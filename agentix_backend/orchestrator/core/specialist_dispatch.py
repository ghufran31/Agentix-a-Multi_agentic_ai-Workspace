"""Fixed Phase 04 adapters. The planner never selects a method or caller identity."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, transaction
from django.db import IntegrityError
from groq import APIError, APITimeoutError
from httpx import TimeoutException
from pydantic import ValidationError

from orchestrator.agents.database.schemas import DatabaseAgentResult, ToolExecutionResult
from orchestrator.agents.matching.schemas import MatchingAgentResult, MatchingRequest, MatchingResponse
from orchestrator.agents.project.agent import execute_project_task
from orchestrator.agents.project.schemas import ProjectAgentResult
from orchestrator.agents.research.agent import execute_research
from orchestrator.agents.research.schemas import ResearchRequest, ResearchResult
from orchestrator.tools.database.project_tools import ProjectIdInput, project_tools
from orchestrator.agents.project.schemas import ProjectAgentOutput, ProjectSpecification
from orchestrator.core.project_mapper import (
    canonical_mapping_payload,
    map_project_specification,
)
from orchestrator.models import ProjectCreationReceipt
from orchestrator.tools.matching.context_tools import context_tools

from .agent_registry import PlanningInput, ProjectCreateInput, ProjectCreateOutput
from companies.models import CompanyUser
from projects.models import Project, ProjectRequirement
from .llm_factory import LLMProviderError
from .permissions import database_context
from .plan_schemas import ExecutionError
from .plan_validator import PlanValidationFailure, validate_plan


class DispatchFailure(Exception):
    def __init__(self, code, message, metadata=None):
        super().__init__(message)
        self.error = ExecutionError(code=code, message=message)
        self.metadata = metadata or {}


def validate_real_plan(plan, registry, context, limits):
    order = validate_plan(
        plan,
        registry,
        context,
        limits,
        require_mock=False,
        allow_approvals=True,
    )
    for task in plan.tasks:
        if not _binding_matches(registry, task.capability):
            raise PlanValidationFailure({
                'error_code': 'real_adapter_missing',
                'rule': 'capability_must_have_approved_real_adapter',
                'task_ids': [task.task_id],
                'capability': task.capability,
            })
    return order


def _binding_matches(registry, capability):
    ensure_real_adapters(registry)
    try:
        agent, cap = registry.lookup(capability)
    except KeyError:
        return False
    return cap.real_adapter is not None


def real_capabilities(registry, context):
    return {
        name for name in registry.visible(context, allow_approvals=True)
        if _binding_matches(registry, name)
    }


def _read_context(context):
    user = get_user_model().objects.filter(pk=context.user_id, is_active=True).first()
    return database_context(
        user,
        context.company_id,
        read_only=not bool(context.permissions & frozenset({'projects.write'})),
    )


def _get_project(inputs, context):
    tool = next(tool for tool in project_tools(context) if tool.name == 'get_project')
    result = ToolExecutionResult.model_validate(dict(tool.invoke(inputs.model_dump())),
                                                strict=True)
    if result.pending_approval is not None:
        raise DispatchFailure('approval_unsupported', 'Approval is unavailable in this phase.')
    if not result.success:
        raise DispatchFailure('not_found', 'Project not found in the authorized company.')
    if result.data.get('project', {}).get('id') != inputs.project_id:
        raise DispatchFailure('invalid_task_output', 'Project tool returned an unexpected record.')
    return DatabaseAgentResult(answer=result.message, tool_names=[tool.name],
                               execution_results=[result]), {'provider_used': False}


def _rank(inputs, context):
    tool = next(tool for tool in context_tools(context) if tool.name == 'rank_project_employees')
    ranking = MatchingResponse.model_validate(tool.invoke(inputs.model_dump()), strict=True)
    if not ranking.success:
        if ranking.error == 'not_found':
            raise DispatchFailure('not_found', 'Project not found in the authorized company.')
        if ranking.error == 'Project requires explicit skills, roles, and a deadline.':
            raise DispatchFailure(
                'incomplete_data',
                'The saved project needs explicit skills, roles, and a deadline before matching.',
            )
        if ranking.error == 'Project skills or roles are malformed.':
            raise DispatchFailure(
                'invalid_project_requirements',
                'The saved project has malformed matching requirements.',
            )
        raise DispatchFailure('matching_failed', 'No valid ranking was produced for the authorized project.')
    if ranking.metadata.project_id != inputs.project_id:
        raise DispatchFailure('invalid_task_output', 'Ranking returned an unexpected project.')
    return MatchingAgentResult(success=True, answer=ranking.answer, structured_output=ranking,
                               tool_names=[tool.name]), {'provider_used': False}


def _plan(inputs, context):
    # This capability grants general planning, not company taxonomy reads.
    task = inputs.task
    if inputs.explicit_deadline is not None:
        task += (
            '\n\nServer-verified explicit user deadline: '
            f'{inputs.explicit_deadline}. Preserve this exact date '
            'in the project specification deadline field.'
        )
    result = execute_project_task(None, task)
    result = ProjectAgentResult.model_validate(result.model_dump() if isinstance(
        result, ProjectAgentResult) else result, strict=True)
    metadata = {'model_requests': result.model_requests, 'model_responses': result.model_calls}
    metadata.update({key: getattr(result, key) for key in (
        'failure_stage', 'provider_status', 'provider_code', 'finish_reason',
    ) if getattr(result, key) is not None})
    if result.failure_stage == 'output_validation':
        metadata['validation_codes'] = result.validation_errors
        if result.validation_issues:
            metadata['validation_issues'] = [item.model_dump() for item in result.validation_issues]
    if result.provider_status == 429:
        raise DispatchFailure('rate_limited', 'The Project Agent provider is rate limited.', metadata)
    if result.provider_status == 413 and result.provider_code == 'rate_limit_exceeded':
        raise DispatchFailure(
            'rate_limited', 'The Project Agent provider rejected the request under its limits.', metadata,
        )
    if not result.success or not result.structured_output:
        raise DispatchFailure('project_planning_failed', 'The Project Agent returned no valid plan.', metadata)
    if result.structured_output.outcome != 'specification':
        outcome = result.structured_output.outcome
        raise DispatchFailure(outcome, 'Project planning did not produce a specification.', metadata)
    return result, metadata


def _create_project(inputs, context):
    scope = _read_context(context)
    if scope.role not in ('owner', 'admin', 'manager'):
        raise DispatchFailure('unauthorized', 'A project writer role is required.')
    if not getattr(context, 'thread_id', None) or not getattr(context, 'execution_id', None):
        raise DispatchFailure('idempotency_context_missing',
                              'The project creation execution identity is missing.')
    task_id = getattr(context, 'task_id', None) or 'unknown'
    try:
        raw_specification = inputs.specification
        if isinstance(raw_specification, dict) and 'outcome' in raw_specification:
            output = ProjectAgentOutput.model_validate(raw_specification, strict=True)
            specification = output.specification
        else:
            specification = ProjectSpecification.model_validate(raw_specification, strict=True)
    except ValidationError as exc:
        raise DispatchFailure('invalid_project_mapping',
                              'The project specification could not be mapped safely.') from exc
    if specification is None:
        raise DispatchFailure(
            'invalid_project_mapping',
            'The Project Agent did not return a specification.',
        )
    specification_deadline = (
        specification.deadline.isoformat() if specification.deadline else None
    )
    if specification_deadline != inputs.trusted_deadline:
        raise DispatchFailure(
            'invalid_project_mapping',
            'The project deadline does not match the explicitly supplied user date.',
        )
    mapping = map_project_specification(specification, company=scope.company)
    payload, _ = canonical_mapping_payload(mapping)
    identity_payload = {
        'company_id': scope.company.id,
        'thread_id': context.thread_id,
        'execution_id': context.execution_id,
        'task_id': task_id,
    }
    encoded = json.dumps(
        identity_payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    )
    from hashlib import sha256
    operation_key = sha256(encoded.encode('utf-8')).hexdigest()

    try:
        with transaction.atomic():
            receipt, created = ProjectCreationReceipt.objects.select_for_update().get_or_create(
                company=scope.company,
                operation_key=operation_key,
                defaults={
                    'thread_id': context.thread_id,
                    'execution_id': context.execution_id,
                    'task_id': task_id,
                    'canonical_payload': payload,
                    'status': ProjectCreationReceipt.Status.PENDING,
                },
            )
            if not created:
                if receipt.canonical_payload != payload:
                    raise DispatchFailure(
                        'idempotency_conflict',
                        'The retry payload conflicts with the original project creation.',
                    )
                if receipt.project_id:
                    project = Project.objects.select_related('company').get(
                        id=receipt.project_id,
                        company=scope.company,
                    )
                    requirements_count = project.requirements.count()
                    return ProjectCreateOutput(
                        project_id=project.id,
                        name=project.name,
                        description=project.description,
                        deadline=project.deadline,
                        specification=specification.model_dump(mode='json'),
                        requirements_created=requirements_count,
                        matched_skills=mapping.matched_skills,
                        unresolved_skills=mapping.unresolved_skills,
                        warnings=mapping.warnings,
                        duplicate_recovered=True,
                    ).model_dump(mode='json'), {
                        'provider_used': False,
                        'duplicate_recovered': True,
                        'operation_key': operation_key,
                    }
                raise DispatchFailure(
                    'idempotency_pending',
                    'The original project creation is not yet committed.',
                )

            project = Project.objects.create(
                company=scope.company,
                name=mapping.name,
                description=mapping.description,
                status=mapping.status,
                priority=mapping.priority,
                deadline=mapping.deadline,
            )
            requirements = []
            for requirement in mapping.requirements:
                requirements.append(ProjectRequirement.objects.create(
                    project=project,
                    requirement=requirement.requirement,
                    required_skills=', '.join(requirement.required_skills) or None,
                    required_roles=', '.join(requirement.required_roles) or None,
                    priority=requirement.priority,
                ))
            receipt.project = project
            receipt.status = ProjectCreationReceipt.Status.COMMITTED
            receipt.save(update_fields=('project', 'status', 'updated_at'))
    except DispatchFailure:
        raise
    except IntegrityError:
        receipt = ProjectCreationReceipt.objects.filter(
            company=scope.company,
            operation_key=operation_key,
        ).select_related('project').first()
        if not receipt or not receipt.project_id:
            raise DispatchFailure(
                'idempotency_conflict',
                'A concurrent project creation could not be recovered.',
            )
        project = receipt.project
        return ProjectCreateOutput(
            project_id=project.id,
            name=project.name,
            description=project.description,
            deadline=project.deadline,
            specification=specification.model_dump(mode='json'),
            requirements_created=project.requirements.count(),
            matched_skills=mapping.matched_skills,
            unresolved_skills=mapping.unresolved_skills,
            warnings=mapping.warnings,
            duplicate_recovered=True,
        ).model_dump(mode='json'), {
            'provider_used': False,
            'duplicate_recovered': True,
            'operation_key': operation_key,
        }

    return ProjectCreateOutput(
        project_id=project.id,
        name=project.name,
        description=project.description,
        deadline=project.deadline,
        specification=specification.model_dump(mode='json'),
        requirements_created=len(requirements),
        matched_skills=mapping.matched_skills,
        unresolved_skills=mapping.unresolved_skills,
        warnings=mapping.warnings,
        duplicate_recovered=False,
    ).model_dump(mode='json'), {
        'provider_used': False,
        'duplicate_recovered': False,
        'operation_key': operation_key,
    }


def _research(inputs, context):
    result = execute_research(inputs.question)
    result = ResearchResult.model_validate(result.model_dump() if isinstance(
        result, ResearchResult) else result, strict=True)
    metadata = {'model_responses': result.model_responses, 'total_tokens': result.tokens,
                'search_requests': sum(item.get('requests', 0) for item in result.tool_results)}
    safe_errors = {
        'BadRequestError', 'GraphRecursionError', 'invalid_summary', 'ungrounded_citation',
        'invalid_tool_response', 'no_grounded_findings', 'no_results', 'search_timeout',
        'search_unavailable', 'search_quota', 'missing_tavily_key', 'tavily_auth_failed',
    }
    diagnostics = [code for code in result.errors if code in safe_errors]
    if diagnostics:
        metadata['research_errors'] = diagnostics
    if result.provider_status is not None:
        metadata['provider_status'] = result.provider_status
    if result.provider_code in {'tool_use_failed', 'rate_limit_exceeded'}:
        metadata['provider_code'] = result.provider_code
    credits = [item['credits'] for item in result.tool_results if type(item.get('credits')) is int]
    if credits:
        metadata['search_credits'] = sum(credits)
    if result.provider_status == 429 or 'search_quota' in result.errors:
        raise DispatchFailure('rate_limited', 'A research provider is rate limited.', metadata)
    if 'search_timeout' in result.errors:
        raise DispatchFailure('specialist_timeout', 'Research timed out.', metadata)
    if result.status == 'error' or not result.summary or not result.summary.findings or not result.sources:
        raise DispatchFailure('research_failed', 'The Research Agent returned no validated findings.', metadata)
    citations = {url for finding in result.summary.findings for url in finding.urls}
    if not citations <= {str(source.url) for source in result.sources}:
        raise DispatchFailure('invalid_task_output', 'Research citations did not match the returned sources.', metadata)
    if result.question != inputs.question.strip():
        raise DispatchFailure('invalid_task_output', 'Research returned an unexpected question.', metadata)
    return result, metadata


ADAPTERS = {
    'database.get_project': _get_project,
    'database.create_project': _create_project,
    'matching.rank': _rank,
    'project.plan': _plan,
    'research.search': _research,
}


def ensure_real_adapters(registry):
    for capability, adapter in ADAPTERS.items():
        try:
            _, registered = registry.lookup(capability)
        except KeyError:
            continue
        if registered.real_adapter is None:
            registry.bind_real_adapter(capability, adapter)


def dispatch_real(registry, capability, inputs, context, *, approval=None):
    if (capability not in registry.visible(context, allow_approvals=True)
            or not _binding_matches(registry, capability)):
        raise DispatchFailure('unauthorized', 'The capability is not authorized for real dispatch.')
    _, registered = registry.lookup(capability)
    if registered.approval_required:
        expected = {
            'status': 'approved',
            'capability': capability,
            'thread_id': context.thread_id,
            'execution_id': context.execution_id,
            'task_id': context.task_id,
            'user_id': context.user_id,
            'company_id': context.company_id,
            'inputs': inputs.model_dump(mode='json'),
        }
        if not approval or any(approval.get(key) != value for key, value in expected.items()):
            raise DispatchFailure(
                'approval_required',
                'The operation requires a matching authenticated approval.',
            )
    close_old_connections()
    try:
        scope = _read_context(context)
        adapter_context = context if capability == 'database.create_project' else scope
        return registered.real_adapter(inputs, adapter_context)
    except PermissionDenied:
        raise DispatchFailure('unauthorized', 'Active company membership is required.') from None
    except (TimeoutError, TimeoutException, APITimeoutError):
        raise DispatchFailure('specialist_timeout', 'The specialist request timed out.') from None
    except (APIError, LLMProviderError) as exc:
        status = getattr(exc, 'status_code', None)
        code = 'rate_limited' if status == 429 else 'specialist_provider_error'
        raise DispatchFailure(code, 'The specialist provider request failed.',
                              {'provider_status': status}) from None
    finally:
        close_old_connections()
