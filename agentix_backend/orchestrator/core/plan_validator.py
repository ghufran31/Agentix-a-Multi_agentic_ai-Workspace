import json
import logging
import re
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

from pydantic import TypeAdapter, ValidationError


logger = logging.getLogger(__name__)


class PlanValidationFailure(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        logger.warning(
            'Supervisor plan validation rejected: %s',
            json.dumps(diagnostic, sort_keys=True, separators=(',', ':')),
            extra={'plan_validation': diagnostic},
        )
        super().__init__('The proposed plan did not pass validation.')


def _safe_label(value):
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value):
        return value
    return None


def _safe_pydantic_errors(exc):
    errors = []
    for item in exc.errors(include_input=False)[:8]:
        location = []
        parts = item.get('loc', ())
        for index, part in enumerate(parts):
            if item.get('type') == 'extra_forbidden' and index == len(parts) - 1:
                location.append('[redacted]')
            elif type(part) is int:
                location.append(part)
            elif isinstance(part, str):
                location.append(_safe_label(part) or '[redacted]')
        error_type = _safe_label(item.get('type'))
        errors.append({'loc': location, 'type': error_type or 'validation_error'})
    return errors


def log_pydantic_validation_failure(rule, exc, *, error_code):
    diagnostic = {
        'error_code': error_code,
        'rule': rule,
        'pydantic_errors': _safe_pydantic_errors(exc),
    }
    logger.warning(
        'Supervisor plan validation rejected: %s',
        json.dumps(diagnostic, sort_keys=True, separators=(',', ':')),
        extra={'plan_validation': diagnostic},
    )
    return diagnostic


def _reject(error_code, rule, *, task=None, task_ids=None, capability=None,
            field=None, dependency=None, source_task_id=None, source_field=None,
            pydantic_errors=None):
    diagnostic = {'error_code': error_code, 'rule': rule}
    if task is not None:
        task_ids = [task.task_id]
        capability = task.capability
    safe_ids = [_safe_label(item) for item in (task_ids or ())]
    if safe_ids:
        diagnostic['task_ids'] = safe_ids
    for key, value in (
        ('capability', capability),
        ('field', field),
        ('dependency', dependency),
        ('source_task_id', source_task_id),
        ('source_field', source_field),
    ):
        safe_value = _safe_label(value)
        if safe_value is not None:
            diagnostic[key] = safe_value
    if pydantic_errors:
        diagnostic['pydantic_errors'] = pydantic_errors
    return PlanValidationFailure(diagnostic)


@dataclass(frozen=True)
class PlanLimits:
    max_tasks: int = 32
    max_depth: int = 12

    def __post_init__(self):
        if not 1 <= self.max_tasks <= 64 or not 1 <= self.max_depth <= 64:
            raise ValueError('Plan limits must be between 1 and 64.')


def validate_plan(plan, registry, context, limits, *, require_mock=True, allow_approvals=False):
    if len(plan.tasks) > limits.max_tasks:
        raise _reject('task_limit_exceeded', 'plan_task_count_within_limit')
    tasks = {task.task_id: task for task in plan.tasks}
    if len(tasks) != len(plan.tasks):
        raise _reject('duplicate_task_id', 'task_ids_must_be_unique')

    capabilities = {}
    visible = registry.visible(context, allow_approvals=allow_approvals)
    for task in plan.tasks:
        try:
            _, cap = registry.lookup(task.capability)
        except KeyError:
            raise _reject('capability_unknown', 'capability_must_be_registered',
                          task=task) from None
        if cap.approval_required and not allow_approvals:
            raise _reject('approval_not_enabled', 'approval_required_capability_needs_approval_mode',
                          task=task)
        if task.capability not in visible:
            raise _reject('capability_not_authorized', 'capability_must_be_visible_to_context',
                          task=task)
        if require_mock and cap.mock_executor is None:
            raise _reject('mock_executor_missing', 'mock_mode_requires_registered_executor',
                          task=task)
        if len(set(task.depends_on)) != len(task.depends_on):
            raise _reject('duplicate_dependency', 'dependencies_must_be_unique', task=task)
        missing_dependencies = sorted(set(task.depends_on) - tasks.keys())
        if missing_dependencies:
            raise _reject('dependency_not_found', 'dependency_must_name_a_plan_task',
                          task=task, dependency=missing_dependencies[0])
        capabilities[task.task_id] = cap

    try:
        order = tuple(TopologicalSorter(
            {task.task_id: task.depends_on for task in plan.tasks}
        ).static_order())
    except CycleError as exc:
        cycle_ids = [
            item for item in (exc.args[1] if len(exc.args) > 1 else ())
            if isinstance(item, str)
        ]
        raise _reject('dependency_cycle', 'dependency_graph_must_be_acyclic',
                      task_ids=cycle_ids) from None

    depths = {}
    for task_id in order:
        task = tasks[task_id]
        depths[task_id] = 1 + max((depths[dep] for dep in task.depends_on), default=0)
        if depths[task_id] > limits.max_depth:
            raise _reject('dependency_depth_exceeded', 'dependency_depth_within_limit',
                          task=task)
        cap = capabilities[task_id]
        fields = cap.input_schema.model_fields
        supplied = task.inputs.keys() | task.references.keys()
        conflicting = task.inputs.keys() & task.references.keys()
        unknown = supplied - fields.keys()
        if conflicting or unknown:
            field_name = sorted(conflicting or unknown)[0]
            raise _reject(
                'task_input_conflict_or_unknown',
                'inputs_must_be_known_and_supplied_once',
                task=task,
                field=field_name,
            )
        missing = sorted(
            name for name, field in fields.items()
            if field.is_required() and name not in supplied
        )
        if missing:
            raise _reject('required_input_missing', 'all_required_inputs_must_be_supplied',
                          task=task, field=missing[0])
        for name, reference in task.references.items():
            if reference.task_id not in task.depends_on:
                raise _reject(
                    'reference_not_direct_dependency',
                    'output_reference_must_target_direct_dependency',
                    task=task,
                    field=name,
                    source_task_id=reference.task_id,
                    source_field=reference.field,
                )
            source_fields = capabilities[reference.task_id].output_schema.model_fields
            if reference.field not in source_fields:
                raise _reject(
                    'reference_output_field_unknown',
                    'output_reference_must_name_declared_top_level_field',
                    task=task,
                    field=name,
                    source_task_id=reference.task_id,
                    source_field=reference.field,
                )
            source_type = TypeAdapter(source_fields[reference.field].rebuild_annotation()).json_schema().get('type')
            target_type = TypeAdapter(fields[name].rebuild_annotation()).json_schema().get('type')
            if source_type and target_type and source_type != target_type and (
                source_type, target_type
            ) != ('integer', 'number'):
                raise _reject(
                    'reference_type_incompatible',
                    'referenced_output_type_must_match_input_type',
                    task=task,
                    field=name,
                    source_task_id=reference.task_id,
                    source_field=reference.field,
                )
        try:
            if task.references:
                for name, value in task.inputs.items():
                    TypeAdapter(fields[name].rebuild_annotation()).validate_python(value, strict=True)
            else:
                cap.input_schema.model_validate(task.inputs, strict=True)
        except ValidationError as exc:
            raise _reject(
                'task_inputs_invalid',
                'task_inputs_must_match_capability_schema',
                task=task,
                pydantic_errors=_safe_pydantic_errors(exc),
            ) from None
    return order
