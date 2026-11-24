from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from companies.models import Company, CompanyUser
from projects.models import Project, ProjectRequirement
from workforce.models import (
    Department,
    Employee,
    EmployeeAIProfile,
    EmployeeSkill,
    Skill,
)
from orchestrator.agents.project.schemas import (
    ProjectAgentOutput,
    ProjectAgentResult,
    ProjectSpecification,
)
from orchestrator.core.execution_context import ExecutionContext
from orchestrator.core.project_mapper import map_project_specification
from orchestrator.core.specialist_dispatch import (
    DispatchFailure,
    _create_project,
    dispatch_real,
)
from orchestrator.core.agent_registry import ProjectCreateInput, specialist_registry
from orchestrator.core.plan_schemas import ExecutionPlan
from orchestrator.core.plan_validator import PlanLimits, validate_plan
from orchestrator.core.specialist_dispatch import validate_real_plan
from orchestrator.models import ProjectCreationReceipt
from orchestrator.graph.checkpoints import open_postgres_checkpoints
from orchestrator.graph.console_journal import setup_console_tables
from orchestrator.graph.conversations import ConversationConflict, SupervisorConversations
from orchestrator.core.permissions import database_context
from orchestrator.ml_engine.loader import load_model
from orchestrator.tools.matching.context_tools import context_tools


def specification(deadline=None):
    return ProjectSpecification.model_validate({
        'name': 'Flutter Commerce',
        'description': 'Flutter e-commerce application.',
        'project_type': 'e-commerce',
        'deadline': deadline.isoformat() if deadline else None,
        'features': [{
            'name': 'Authentication',
            'description': 'Secure user authentication.',
            'priority': 'must',
            'source': 'user',
        }],
        'functional_requirements': [{
            'identifier': 'FR-001',
            'description': 'Allow users to authenticate.',
            'related_features': ['Authentication'],
            'priority': 'must',
            'source': 'user',
        }],
        'technology_stack': {
            'architecture_style': 'API-backed mobile application',
            'choices': [{
                'layer': 'mobile',
                'name': 'Flutter',
                'purpose': 'Mobile user interface',
                'rationale': 'Requested platform.',
                'source': 'user_required',
            }],
        },
        'required_roles': [{
            'name': 'Mobile Engineer',
            'responsibilities': ['Build the Flutter application.'],
            'skills': ['Flutter'],
            'suggested_count': 1,
        }],
        'required_skills': [{
            'name': 'Flutter',
            'category': 'Technical',
            'roles': ['Mobile Engineer'],
            'taxonomy_status': 'proposed',
        }],
        'milestones': [{
            'name': 'MVP',
            'objective': 'Deliver authentication.',
            'deliverables': ['Working authentication'],
            'dependencies': [],
            'estimated_duration_weeks': 2,
        }],
        'limitations': [],
    })


class ProjectCreationWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='project-workflow-owner',
            password='test-pass',
        )
        self.member = user_model.objects.create_user(
            username='project-workflow-member',
            password='test-pass',
        )
        self.company = Company.objects.create(
            created_by_user=self.owner,
            name='Workflow Company',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=self.owner,
            role=CompanyUser.Role.OWNER,
        )
        CompanyUser.objects.create(
            company=self.company,
            user=self.member,
            role=CompanyUser.Role.MEMBER,
        )

    def context(self, user=None):
        user = user or self.owner
        return ExecutionContext(
            user_id=user.pk,
            company_id=self.company.pk,
            allowed_capabilities=frozenset({'database.create_project', 'matching.rank'}),
            permissions=frozenset({'projects.write', 'projects.read', 'workforce.read'}),
            thread_id='agentix:test:workflow',
            execution_id='workflow-execution',
            task_id='create_project',
        )

    def test_mapper_maps_supported_fields_and_reports_unknown_skill(self):
        mapping = map_project_specification(specification(), company=self.company)
        self.assertEqual(mapping.name, 'Flutter Commerce')
        self.assertEqual(mapping.status, 'draft')
        self.assertEqual(mapping.requirements[0].requirement,
                         'Allow users to authenticate.')
        self.assertIn('Flutter', mapping.unresolved_skills)
        self.assertIn('Flutter', mapping.requirements[0].required_skills)
        self.assertTrue(mapping.warnings)

    def test_mapper_preserves_explicit_deadline(self):
        deadline = date.today() + timedelta(days=30)
        mapping = map_project_specification(
            specification(deadline=deadline),
            company=self.company,
        )
        self.assertEqual(mapping.deadline, deadline)

    def test_mapper_uses_company_skill_records_not_llm_taxonomy_claims(self):
        skill = Skill.objects.create(company=self.company, name='Flutter')
        known_mapping = map_project_specification(specification(), company=self.company)
        self.assertEqual(known_mapping.matched_skills, ['Flutter'])
        self.assertEqual(known_mapping.unresolved_skills, [])

        false_claim = specification().model_copy(update={
            'required_skills': [
                specification().required_skills[0].model_copy(update={
                    'name': 'Invented Skill',
                    'taxonomy_status': 'existing',
                    'existing_skill_id': skill.pk,
                })
            ]
        })
        unresolved = map_project_specification(false_claim, company=self.company)
        self.assertEqual(unresolved.matched_skills, [])
        self.assertEqual(unresolved.unresolved_skills, ['Invented Skill'])
        self.assertEqual(
            unresolved.requirements[0].required_skills,
            ['Invented Skill'],
        )

    def test_unauthorized_member_cannot_create_project(self):
        from orchestrator.core.specialist_dispatch import DispatchFailure

        context = ExecutionContext(
            user_id=self.member.pk,
            company_id=self.company.pk,
            allowed_capabilities=frozenset({'database.create_project'}),
            permissions=frozenset(),
            thread_id='agentix:test:member',
            execution_id='member-execution',
            task_id='create_project',
        )
        with self.assertRaises(DispatchFailure) as raised:
            _create_project(
                ProjectCreateInput(specification=specification().model_dump(mode='json')),
                context,
            )
        self.assertEqual(raised.exception.error.code, 'unauthorized')
        self.assertFalse(Project.objects.filter(company=self.company).exists())

    def test_real_dispatch_requires_matching_approval_record(self):
        context = self.context()
        with self.assertRaises(DispatchFailure) as raised:
            dispatch_real(
                specialist_registry(),
                'database.create_project',
                ProjectCreateInput(
                    specification=specification().model_dump(mode='json'),
                ),
                context,
            )
        self.assertEqual(raised.exception.error.code, 'approval_required')
        self.assertFalse(Project.objects.filter(company=self.company).exists())

    def test_creation_rejects_untrusted_or_invalid_deadline(self):
        dated = specification(deadline=date.today() + timedelta(days=30))
        with self.assertRaises(ValidationError):
            ProjectCreateInput(specification=dated.model_dump(mode='json'))
        with self.assertRaises(ValidationError):
            ProjectCreateInput(
                specification=specification().model_dump(mode='json'),
                trusted_deadline='2027-02-30',
            )
        self.assertFalse(Project.objects.filter(company=self.company).exists())

    def test_atomic_create_and_retry_is_idempotent(self):
        inputs = ProjectCreateInput(
            specification=specification().model_dump(mode='json'),
        )
        output, metadata = _create_project(inputs, self.context())
        self.assertEqual(Project.objects.filter(company=self.company).count(), 1)
        project = Project.objects.get(company=self.company)
        self.assertEqual(project.name, 'Flutter Commerce')
        self.assertEqual(project.requirements.count(), 1)
        retry, retry_metadata = _create_project(inputs, self.context())
        self.assertTrue(retry['duplicate_recovered'])
        self.assertTrue(retry_metadata['duplicate_recovered'])
        self.assertEqual(retry['project_id'], output['project_id'])
        self.assertEqual(Project.objects.filter(company=self.company).count(), 1)

    def test_saved_project_reference_is_validated_for_matching(self):
        plan = ExecutionPlan.model_validate({
            'goal': 'Create and rank a project',
            'tasks': [
                {
                    'task_id': 'create',
                    'capability': 'database.create_project',
                    'description': 'Create the generated project.',
                    'inputs': {
                        'specification': specification().model_dump(mode='json'),
                        'top_n': 5,
                    },
                    'depends_on': [],
                },
                {
                    'task_id': 'rank',
                    'capability': 'matching.rank',
                    'description': 'Rank employees for the saved project.',
                    'inputs': {'top_n': 5},
                    'references': {
                        'project_id': {
                            'task_id': 'create',
                            'field': 'project_id',
                        }
                    },
                    'depends_on': ['create'],
                },
            ],
        })
        registry = specialist_registry()
        order = validate_real_plan(
            plan,
            registry,
            self.context(),
            PlanLimits(),
        )
        self.assertEqual(order, ('create', 'rank'))

    def test_conflicting_retry_payload_is_rejected(self):
        inputs = ProjectCreateInput(
            specification=specification().model_dump(mode='json'),
        )
        _create_project(inputs, self.context())
        changed = specification()
        changed.name = 'Different Project'
        with self.assertRaises(DispatchFailure) as raised:
            _create_project(
                ProjectCreateInput(specification=changed.model_dump(mode='json')),
                self.context(),
            )
        self.assertEqual(raised.exception.error.code, 'idempotency_conflict')
        self.assertEqual(Project.objects.filter(company=self.company).count(), 1)


class ProjectWorkflowDatabaseFixtures:
    """Use committed transactions without Django's whole-database test flush."""

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('These reliability tests require PostgreSQL.')
        if connection.settings_dict['NAME'] != 'test_Agentix':
            self.skipTest('These reliability tests require test_Agentix.')
        self.user_ids = []
        self.company_ids = []
        self.membership_ids = []
        self.department_ids = []
        self.employee_ids = []
        self.profile_ids = []
        self.skill_ids = []
        self.employee_skill_ids = []
        self.requirement_ids = []
        self.receipt_ids = []
        self.project_ids = []
        self.addCleanup(self._cleanup_records)
        self.user = get_user_model().objects.create_user(
            username='workflow-reliability-owner',
            password='test-pass',
        )
        self.user_ids.append(self.user.pk)
        self.company = Company.objects.create(
            created_by_user=self.user,
            name='Workflow Reliability Company',
        )
        self.company_ids.append(self.company.pk)
        membership = CompanyUser.objects.create(
            company=self.company,
            user=self.user,
            role=CompanyUser.Role.OWNER,
        )
        self.membership_ids.append(membership.pk)

    def _cleanup_records(self):
        ProjectCreationReceipt.objects.filter(company_id__in=self.company_ids).delete()
        ProjectRequirement.objects.filter(pk__in=self.requirement_ids).delete()
        Project.objects.filter(pk__in=self.project_ids).delete()
        EmployeeSkill.objects.filter(pk__in=self.employee_skill_ids).delete()
        EmployeeAIProfile.objects.filter(pk__in=self.profile_ids).delete()
        Employee.objects.filter(pk__in=self.employee_ids).delete()
        Department.objects.filter(pk__in=self.department_ids).delete()
        Skill.objects.filter(pk__in=self.skill_ids).delete()
        CompanyUser.objects.filter(pk__in=self.membership_ids).delete()
        Company.objects.filter(pk__in=self.company_ids).delete()
        get_user_model().objects.filter(pk__in=self.user_ids).delete()

    def _fixture_teardown(self):
        if hasattr(self, 'company_ids'):
            self._cleanup_records()

    def context(self, **overrides):
        values = {
            'user_id': self.user.pk,
            'company_id': self.company.pk,
            'allowed_capabilities': frozenset({'database.create_project'}),
            'permissions': frozenset({'projects.write'}),
            'thread_id': 'agentix:reliability:thread',
            'execution_id': 'reliability-execution',
            'task_id': 'create_project',
        }
        values.update(overrides)
        return ExecutionContext(**values)

    def inputs(self, spec=None):
        return ProjectCreateInput(
            specification=(spec or specification()).model_dump(mode='json'),
        )


class SafeProjectTransactionTests(ProjectWorkflowDatabaseFixtures, TransactionTestCase):
    def test_duplicate_retry_recovers_original_commit(self):
        first, _ = _create_project(self.inputs(), self.context())
        self.project_ids.append(first['project_id'])
        recovered, metadata = _create_project(self.inputs(), self.context())
        self.assertTrue(recovered['duplicate_recovered'])
        self.assertTrue(metadata['duplicate_recovered'])
        self.assertEqual(recovered['project_id'], first['project_id'])
        self.assertEqual(Project.objects.filter(company=self.company).count(), 1)

    def test_transaction_rolls_back_project_requirements_and_receipt(self):
        with patch(
            'orchestrator.core.specialist_dispatch.ProjectRequirement.objects.create',
            side_effect=RuntimeError('test rollback'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'test rollback'):
                _create_project(self.inputs(), self.context())
        self.assertFalse(Project.objects.filter(company=self.company).exists())
        self.assertFalse(
            ProjectCreationReceipt.objects.filter(company=self.company).exists()
        )

    def test_concurrent_duplicate_creations_commit_one_project(self):
        barrier = Barrier(2)
        inputs = self.inputs()
        context = self.context()

        def create():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return _create_project(inputs, context)[0]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=30) for future in (
                pool.submit(create),
                pool.submit(create),
            )]
        self.project_ids.append(results[0]['project_id'])
        self.assertEqual(
            {result['project_id'] for result in results},
            {results[0]['project_id']},
        )
        self.assertEqual(Project.objects.filter(company=self.company).count(), 1)
        self.assertEqual(
            ProjectCreationReceipt.objects.filter(company=self.company).count(),
            1,
        )


class ProjectApprovalGraphTests(ProjectWorkflowDatabaseFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(
            company=self.company,
            name='Workflow Engineering',
        )
        self.department_ids.append(self.department.pk)
        self.skill = Skill.objects.create(company=self.company, name='Flutter')
        self.skill_ids.append(self.skill.pk)
        _, metadata = load_model()
        self.job_title = metadata['categories']['job_title'][0]
        self.employee = Employee.objects.create(
            department=self.department,
            employee_code='workflow-eligible',
            first_name='Workflow',
            last_name='Employee',
        )
        self.employee_ids.append(self.employee.pk)
        self.profile = EmployeeAIProfile.objects.create(
            employee=self.employee,
            job_title=self.job_title,
            experience_years=4,
            performance_score=80,
            availability_status='available',
            current_workload=20,
            previous_project_score=75,
            completed_projects=3,
        )
        self.profile_ids.append(self.profile.pk)
        self.employee_skill = EmployeeSkill.objects.create(
            employee=self.employee,
            skill=self.skill,
            proficiency=4,
            years_experience=3,
        )
        self.employee_skill_ids.append(self.employee_skill.pk)
        self.registry = specialist_registry()
        self.caps = {
            'database.create_project',
            'matching.rank',
            'project.plan',
        }
        self.permissions = {
            'projects.write',
            'projects.read',
            'workforce.read',
            'approvals.decide',
        }
        self.plan = {
            'goal': 'Prepare, approve, save, and match the project.',
            'tasks': [
                {
                    'task_id': 'draft',
                    'capability': 'project.plan',
                    'description': 'Generate the project specification.',
                    'inputs': {'task': 'Create a Flutter e-commerce project.'},
                    'depends_on': [],
                },
                {
                    'task_id': 'save',
                    'capability': 'database.create_project',
                    'description': 'Save the approved project.',
                    'inputs': {'top_n': 5},
                    'references': {
                        'specification': {
                            'task_id': 'draft',
                            'field': 'structured_output',
                        }
                    },
                    'depends_on': ['draft'],
                },
                {
                    'task_id': 'rank',
                    'capability': 'matching.rank',
                    'description': 'Rank employees for the saved project.',
                    'inputs': {'top_n': 5},
                    'references': {
                        'project_id': {'task_id': 'save', 'field': 'project_id'}
                    },
                    'depends_on': ['save'],
                },
            ],
        }

    def service(self, store):
        return SupervisorConversations(
            self.registry,
            store,
            mode='real',
            planner=type('FixedPlanner', (), {
                'invoke': lambda _self, _messages: {
                    'parsed': {
                        'outcome': 'plan',
                        'response': 'Prepared a dependent project workflow.',
                        'plan': self.plan,
                    },
                    'raw': AIMessage(content=''),
                }
            })(),
            grants=lambda _scope: (self.caps, self.permissions),
        )

    def test_approval_resume_persists_deadline_and_matching_reads_it(self):
        deadline = date.today() + timedelta(days=30)
        self.specification = specification().model_copy(update={
            'deadline': deadline,
            'required_roles': [
                specification().required_roles[0].model_copy(update={
                    'name': self.job_title,
                })
            ]
        })
        generated = ProjectAgentResult(
            answer='Structured project specification.',
            structured_output=ProjectAgentOutput(
                outcome='specification',
                response='Specification ready.',
                specification=self.specification,
            ),
        )
        observed_project_ids = []
        original_context_tools = __import__(
            'orchestrator.core.specialist_dispatch',
            fromlist=['context_tools'],
        ).context_tools

        def record_matching_context(scope):
            tools = original_context_tools(scope)
            output = []
            for tool in tools:
                if tool.name == 'rank_project_employees':
                    rank_tool = tool

                    class ToolSpy:
                        name = rank_tool.name

                        def invoke(self, arguments):
                            observed_project_ids.append(arguments['project_id'])
                            return rank_tool.invoke(arguments)

                    output.append(ToolSpy())
                else:
                    output.append(tool)
            return output

        with open_postgres_checkpoints() as store:
            app = self.service(store)
            thread = app.create_thread(self.user, self.company.pk)
            thread_id = app._config(thread, app._context(self.user, self.company.pk))[
                'configurable'
            ]['thread_id']
            try:
                with patch(
                    'orchestrator.core.specialist_dispatch.execute_project_task',
                    return_value=generated,
                ) as execute:
                    pending = app.turn(
                        thread,
                        self.user,
                        self.company.pk,
                        f'Create a Flutter e-commerce project with deadline {deadline.isoformat()} '
                        'and recommend employees.',
                        execution_id='approval-graph-verification',
                    )
                    execute.assert_called_once()
                    self.assertIn(
                        f'Server-verified explicit user deadline: {deadline.isoformat()}',
                        execute.call_args.args[1],
                    )
                    self.assertEqual(
                        len(pending['pending_approvals']),
                        1,
                        {
                            'errors': pending.get('errors'),
                            'decision': pending.get('decision'),
                            'statuses': pending.get('task_statuses'),
                            'results': pending.get('results'),
                        },
                    )
                    proposal, = pending['pending_approvals']
                    self.assertEqual(pending['results']['draft'].status, 'done')
                    self.assertFalse(
                        Project.objects.filter(company=self.company).exists()
                    )
                    self.assertEqual(proposal['review']['project_name'], 'Flutter Commerce')
                    self.assertEqual(proposal['review']['deadline'], deadline.isoformat())
                    self.assertIn('deadline', proposal['review']['fields_saved'])
                    self.assertEqual(proposal['review']['skills'], ['Flutter'])
                    self.assertIn(
                        'technology_stack',
                        proposal['review']['additional_fields_not_persisted'],
                    )
                    self.assertFalse(proposal['review']['persistence_performed'])
                    with store.connection.cursor() as cursor:
                        cursor.execute(
                            'SELECT COUNT(*) AS count FROM agentix_checkpoints.checkpoints '
                            'WHERE thread_id = %s',
                            (proposal['thread_id'],),
                        )
                        self.assertGreater(cursor.fetchone()['count'], 0)

                    with patch(
                        'orchestrator.core.specialist_dispatch.context_tools',
                        side_effect=record_matching_context,
                    ):
                        completed = app.resume(
                            thread,
                            self.user,
                            self.company.pk,
                            approval_id=proposal['approval_id'],
                            execution_id=proposal['execution_id'],
                            approved=True,
                        )
                    project_result = completed['results']['save']
                    self.assertEqual(
                        project_result.status,
                        'done',
                        completed['results'],
                    )
                    project_id = project_result.output['project_id']
                    self.project_ids.append(project_id)
                    project = Project.objects.get(
                        pk=project_id,
                        company=self.company,
                    )
                    self.assertEqual(project.deadline, deadline)
                    self.assertEqual(project_result.output['deadline'], deadline.isoformat())
                    self.assertEqual(project.requirements.count(), 1)
                    requirement = project.requirements.get()
                    self.requirement_ids.append(requirement.pk)
                    self.assertEqual(requirement.required_skills, 'Flutter')
                    self.assertEqual(requirement.required_roles, self.job_title)
                    matching_context = next(
                        tool for tool in context_tools(database_context(
                            self.user, self.company.pk, read_only=True,
                        ))
                        if tool.name == 'get_project_matching_context'
                    ).invoke({'project_id': project.pk})
                    self.assertEqual(matching_context['project']['deadline'], deadline.isoformat())
                    self.assertEqual(
                        matching_context['project']['requirements'][0]['required_skills'],
                        'Flutter',
                    )
                    self.assertEqual(
                        matching_context['project']['requirements'][0]['required_roles'],
                        self.job_title,
                    )
                    receipt = ProjectCreationReceipt.objects.get(project=project)
                    self.receipt_ids.append(receipt.pk)
                    self.assertEqual(observed_project_ids, [project.pk])
                    self.assertEqual(completed['results']['rank'].status, 'done')
                    ranking = completed['results']['rank'].output['structured_output']
                    self.assertEqual(ranking['metadata']['project_id'], project.pk)
                    self.assertEqual(ranking['metadata']['ranked_count'], 1)
                    self.assertEqual(ranking['candidates'][0]['employee_id'], self.employee.pk)
                    self.assertIn('Project saved: Flutter Commerce', completed['final_response'])
                    self.assertIn(f'Deadline: {deadline.isoformat()}.', completed['final_response'])
                    with self.assertRaises(ConversationConflict):
                        app.resume(
                            thread,
                            self.user,
                            self.company.pk,
                            approval_id=proposal['approval_id'],
                            execution_id=proposal['execution_id'],
                            approved=True,
                        )
                    self.assertEqual(
                        Project.objects.filter(company=self.company).count(),
                        1,
                    )
            finally:
                store.saver.delete_thread(thread_id)
                with store.connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT COUNT(*) AS count FROM agentix_checkpoints.checkpoints '
                        'WHERE thread_id = %s',
                        (thread_id,),
                    )
                    self.assertEqual(cursor.fetchone()['count'], 0)

    def test_matching_creation_without_deadline_asks_before_agent_or_write(self):
        with open_postgres_checkpoints() as store:
            app = self.service(store)
            thread = app.create_thread(self.user, self.company.pk)
            thread_id = app._config(thread, app._context(self.user, self.company.pk))[
                'configurable'
            ]['thread_id']
            try:
                with patch(
                    'orchestrator.core.specialist_dispatch.execute_project_task',
                ) as execute:
                    result = app.turn(
                    thread,
                    self.user,
                    self.company.pk,
                    'Create a Flutter e-commerce project and recommend employees.',
                    execution_id='missing-deadline-verification',
                    )
                self.assertEqual(result['decision'].outcome, 'clarification')
                self.assertIn('YYYY-MM-DD', result['final_response'])
                self.assertFalse(result['pending_approvals'])
                self.assertFalse(result['results'])
                execute.assert_not_called()
                self.assertFalse(Project.objects.filter(company=self.company).exists())
            finally:
                store.saver.delete_thread(thread_id)

    def test_deadline_is_required_when_planner_omits_requested_matching_task(self):
        complete_plan = self.plan
        self.plan = {
            'goal': 'Prepare and save the project.',
            'tasks': [
                complete_plan['tasks'][0],
                complete_plan['tasks'][1],
            ],
        }
        try:
            with open_postgres_checkpoints() as store:
                app = self.service(store)
                thread = app.create_thread(self.user, self.company.pk)
                thread_id = app._config(thread, app._context(self.user, self.company.pk))[
                    'configurable'
                ]['thread_id']
                try:
                    with patch(
                        'orchestrator.core.specialist_dispatch.execute_project_task',
                    ) as execute:
                        result = app.turn(
                            thread,
                            self.user,
                            self.company.pk,
                            'Create a Flutter e-commerce project and recommend employees.',
                            execution_id='omitted-matching-deadline-verification',
                        )
                    self.assertEqual(result['decision'].outcome, 'clarification')
                    self.assertIn('YYYY-MM-DD', result['final_response'])
                    self.assertFalse(result['pending_approvals'])
                    execute.assert_not_called()
                    self.assertFalse(Project.objects.filter(company=self.company).exists())
                finally:
                    store.saver.delete_thread(thread_id)
        finally:
            self.plan = complete_plan

    def test_invalid_matching_deadline_asks_before_agent_or_write(self):
        with open_postgres_checkpoints() as store:
            app = self.service(store)
            thread = app.create_thread(self.user, self.company.pk)
            thread_id = app._config(thread, app._context(self.user, self.company.pk))[
                'configurable'
            ]['thread_id']
            try:
                with patch(
                    'orchestrator.core.specialist_dispatch.execute_project_task',
                ) as execute:
                    result = app.turn(
                    thread,
                    self.user,
                    self.company.pk,
                    'Create a Flutter e-commerce project with deadline 2027-02-30 '
                    'and recommend employees.',
                    execution_id='invalid-deadline-verification',
                    )
                self.assertEqual(result['decision'].outcome, 'clarification')
                self.assertIn('valid project deadline', result['final_response'])
                self.assertFalse(result['pending_approvals'])
                execute.assert_not_called()
                self.assertFalse(Project.objects.filter(company=self.company).exists())
            finally:
                store.saver.delete_thread(thread_id)

    def test_nonwriter_cannot_plan_project_write_capability(self):
        member = get_user_model().objects.create_user(
            username='workflow-reliability-member',
            password='test-pass',
        )
        self.user_ids.append(member.pk)
        membership = CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.membership_ids.append(membership.pk)
        with open_postgres_checkpoints() as store:
            app = self.service(store)
            thread = app.create_thread(member, self.company.pk)
            thread_id = app._config(thread, app._context(member, self.company.pk))[
                'configurable'
            ]['thread_id']
            try:
                with patch(
                    'orchestrator.core.specialist_dispatch.execute_project_task',
                ) as execute:
                    result = app.turn(
                        thread,
                        member,
                        self.company.pk,
                        'Create a project.',
                        execution_id='unauthorized-write-verification',
                    )
                self.assertEqual(result['decision'].outcome, 'planning_error')
                self.assertFalse(
                    Project.objects.filter(company=self.company).exists()
                )
                execute.assert_not_called()
            finally:
                store.saver.delete_thread(thread_id)
                with store.connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT COUNT(*) AS count FROM agentix_checkpoints.checkpoints '
                        'WHERE thread_id = %s',
                        (thread_id,),
                    )
                    self.assertEqual(cursor.fetchone()['count'], 0)

    def test_rejected_project_approval_creates_no_business_records(self):
        deadline = date.today() + timedelta(days=30)
        generated = ProjectAgentResult(
            answer='Structured project specification.',
            structured_output=ProjectAgentOutput(
                outcome='specification',
                response='Specification ready.',
                specification=specification(deadline=deadline),
            ),
        )
        with open_postgres_checkpoints() as store:
            app = self.service(store)
            thread = app.create_thread(self.user, self.company.pk)
            thread_id = app._config(thread, app._context(self.user, self.company.pk))[
                'configurable'
            ]['thread_id']
            try:
                with patch(
                    'orchestrator.core.specialist_dispatch.execute_project_task',
                    return_value=generated,
                ):
                    pending = app.turn(
                        thread,
                        self.user,
                        self.company.pk,
                        f'Create a Flutter e-commerce project with deadline {deadline.isoformat()}.',
                        execution_id='rejected-project-verification',
                    )
                    proposal, = pending['pending_approvals']
                    self.assertFalse(
                        Project.objects.filter(company=self.company).exists()
                    )
                    rejected = app.resume(
                        thread,
                        self.user,
                        self.company.pk,
                        approval_id=proposal['approval_id'],
                        execution_id=proposal['execution_id'],
                        approved=False,
                    )
                self.assertEqual(
                    rejected['approval_records']['save']['status'],
                    'rejected',
                )
                self.assertEqual(rejected['results']['save'].status, 'blocked')
                self.assertEqual(rejected['results']['rank'].status, 'blocked')
                self.assertFalse(Project.objects.filter(company=self.company).exists())
                with self.assertRaises(ConversationConflict):
                    app.resume(
                        thread,
                        self.user,
                        self.company.pk,
                        approval_id=proposal['approval_id'],
                        execution_id=proposal['execution_id'],
                        approved=True,
                    )
            finally:
                store.saver.delete_thread(thread_id)
                with store.connection.cursor() as cursor:
                    cursor.execute(
                        'SELECT COUNT(*) AS count FROM agentix_checkpoints.checkpoints '
                        'WHERE thread_id = %s',
                        (thread_id,),
                    )
                    self.assertEqual(cursor.fetchone()['count'], 0)

    def test_browser_api_explicit_deadline_and_approval(self):
        self._browser_approval_flow(with_deadline=True)

    def test_browser_api_date_reply_resumes_original_request(self):
        self._browser_approval_flow(with_deadline=False)

    @override_settings(ALLOWED_HOSTS=['testserver'],
                       AGENTIX_SUPERVISOR_CONSOLE_ENABLED=True,
                       AGENTIX_SUPERVISOR_CONSOLE_MODE='real',
                       AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES=True,
                       SUPERVISOR_FALLBACK_ENABLED=False)
    @patch('orchestrator.graph.planner.get_llm')
    @patch('orchestrator.graph.planner.structured_llm')
    @patch('orchestrator.core.specialist_dispatch.execute_project_task')
    def _browser_approval_flow(self, project_model, planner, factory, *, with_deadline):
        user = self.user
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        deadline = date.today() + timedelta(days=30)
        spec = specification(deadline)
        project_model.return_value = ProjectAgentResult(
            answer='Draft prepared.',
            structured_output=ProjectAgentOutput(
                outcome='specification', response='Draft prepared.', specification=spec,
            ),
        )
        planner.return_value.invoke.return_value = {'parsed': {
            'outcome': 'clarification', 'response': 'Do you approve saving the project?',
        }}
        with open_postgres_checkpoints() as store:
            setup_console_tables(store.connection)
            client = Client(enforce_csrf_checks=True)
            client.force_login(user)
            session = client.session
            self.addCleanup(session.delete, session.session_key)
            base = '/dev/supervisor/'
            page = client.get(base)
            self.assertContains(page, 'test_Agentix writes with approval')
            headers = {'HTTP_X_CSRFTOKEN': page.cookies['csrftoken'].value}
            api = base + 'api/v1/conversations/'

            def post(url, payload):
                return client.post(url, payload, content_type='application/json', **headers)

            opened = post(api, {})
            self.assertEqual(opened.status_code, 201, opened.content)
            thread = opened.json()['thread']
            mode, company_id, user_id, identifier = signing.loads(thread, salt=SupervisorConversations._salt)
            storage_thread = f'agentix:{mode}:{company_id}:{user_id}:{identifier}'
            url = f'{api}{thread}/'
            try:
                original = 'Create a Flutter e-commerce project and recommend five employees.'
                message = f'{original} Project deadline: {deadline.isoformat()}.' if with_deadline else original
                request = {'request_id': str(uuid4()), 'message': message}
                response = post(url + 'messages/', request)
                self.assertEqual(response.status_code, 200, response.content)
                if not with_deadline:
                    self.assertEqual(client.get(url + 'execution/').json()['status'], 'clarification')
                    reply = {'request_id': str(uuid4()), 'message': 'yes'}
                    self.assertEqual(post(url + 'messages/', reply).status_code, 200)
                    self.assertEqual(client.get(url + 'execution/').json()['status'], 'clarification')
                    project_model.assert_not_called()
                    planner.return_value.invoke.assert_not_called()
                    request = {'request_id': str(uuid4()), 'message': deadline.isoformat()}
                    response = post(url + 'messages/', request)
                    self.assertEqual(response.status_code, 200, response.content)
                self.assertIn(original, project_model.call_args.args[1])
                self.assertIn(deadline.isoformat(), project_model.call_args.args[1])
                state = client.get(url + 'execution/').json()
                self.assertEqual(state['status'], 'awaiting_approval')
                proposal, = state['pending_approvals']
                self.assertEqual(proposal['review']['project_name'], spec.name)
                self.assertEqual(proposal['review']['deadline'], deadline.isoformat())
                self.assertNotIn('operation_key', proposal)
                self.assertNotIn('inputs', proposal)
                self.assertFalse(Project.objects.filter(company=self.company).exists())
                self.assertEqual(post(url + 'messages/', {
                    'request_id': str(uuid4()), 'message': 'yes',
                }).status_code, 409)
                self.assertFalse(Project.objects.filter(company=self.company).exists())
                decision = {key: proposal[key] for key in ('approval_id', 'execution_id')}
                decision['approved'] = True
                membership = CompanyUser.objects.get(user=user, company=self.company)
                membership.role = CompanyUser.Role.MEMBER
                membership.save(update_fields=['role'])
                self.assertEqual(post(url + 'approval/', decision).status_code, 403)
                membership.role = CompanyUser.Role.OWNER
                membership.save(update_fields=['role'])
                response = post(url + 'approval/', decision)
                self.project_ids.extend(Project.objects.filter(company=self.company).values_list('pk', flat=True))
                self.assertEqual(response.status_code, 200, response.content)
                complete = client.get(url + 'execution/').json()
                self.assertEqual(complete['status'], 'done', complete)
                tasks = {item['task_id']: item for item in complete['plan']['tasks']}
                saved = tasks['save']['output']
                self.assertEqual(saved['deadline'], deadline.isoformat())
                self.assertEqual(saved['project_id'], self.project_ids[0])
                self.assertEqual(tasks['rank']['output']['ranked_count'], 1)
                self.assertEqual(post(url + 'approval/', decision).status_code, 409)
                self.assertEqual(post(url + 'messages/', request).status_code, 200)
                self.assertEqual(Project.objects.filter(company=self.company).count(), 1)
                self.assertEqual(ProjectCreationReceipt.objects.filter(company=self.company).count(), 1)
                project_model.assert_called_once()
            finally:
                store.connection.execute('DELETE FROM console_events WHERE thread=%s', (thread,))
                store.connection.execute('DELETE FROM console_threads WHERE thread=%s', (thread,))
                store.saver.delete_thread(storage_thread)
