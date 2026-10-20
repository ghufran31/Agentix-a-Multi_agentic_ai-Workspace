from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .admin import ProjectAdminForm, ProjectMemberAdminForm
from agents.models import AIAgent
from companies.models import Company, CompanyUser
from workforce.models import Department, Employee
from .models import Project, ProjectMember, ProjectRequirement


User = get_user_model()


class ProjectApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='project-owner',
            email='project-owner@example.com',
            password='Safe-project-password-123!',
        )
        self.company = self.create_company(self.owner, 'Project company')
        self.project = Project.objects.create(
            company=self.company,
            name='Initial project',
        )
        self.department = Department.objects.create(
            company=self.company,
            name='Engineering',
        )
        self.employee = Employee.objects.create(
            department=self.department,
            employee_code='PROJECT-001',
            first_name='Casey',
            last_name='Employee',
        )
        self.agent = AIAgent.objects.create(
            company=self.company,
            name='Project agent',
        )
        self.client.force_authenticate(self.owner)

    def create_company(self, user, name):
        company = Company.objects.create(created_by_user=user, name=name)
        CompanyUser.objects.create(
            company=company,
            user=user,
            role=CompanyUser.Role.OWNER,
        )
        return company

    def create_other_company(self):
        user = User.objects.create_user(
            username='other-project-owner',
            email='other-project-owner@example.com',
            password='Safe-project-password-123!',
        )
        company = self.create_company(user, 'Other project company')
        project = Project.objects.create(company=company, name='Private project')
        department = Department.objects.create(company=company, name='Other dept')
        employee = Employee.objects.create(
            department=department,
            employee_code='OTHER-001',
            first_name='Taylor',
            last_name='Employee',
        )
        agent = AIAgent.objects.create(company=company, name='Private agent')
        return company, project, employee, agent

    def test_project_crud_defaults_and_optional_fields(self):
        create = self.client.post(
            reverse('project-list'),
            {
                'company': self.company.pk,
                'name': 'New project',
                'description': 'Project description',
                'start_date': '2026-10-20',
                'deadline': '2026-12-31',
            },
        )
        project_id = create.data['id']
        detail_url = reverse('project-detail', args=(project_id,))
        retrieve = self.client.get(detail_url)
        listing = self.client.get(reverse('project-list'))
        update = self.client.patch(detail_url, {'priority': 'high'})
        delete = self.client.delete(detail_url)

        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create.data['status'], 'draft')
        self.assertEqual(create.data['priority'], 'medium')
        self.assertTrue(create.data['created_at'])
        self.assertEqual(create.data['deadline'], '2026-12-31')
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertIn(self.project.pk, [item['id'] for item in listing.data])
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['priority'], 'high')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)

    def test_project_required_fields_and_company_membership(self):
        missing_name = self.client.post(
            reverse('project-list'),
            {'company': self.company.pk},
        )
        _, _, other_employee, _ = self.create_other_company()
        unauthorized_company = self.client.post(
            reverse('project-list'),
            {'company': other_employee.department.company_id, 'name': 'Rejected'},
        )

        self.assertEqual(missing_name.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', missing_name.data)
        self.assertEqual(unauthorized_company.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('company', unauthorized_company.data)

    def test_project_list_and_detail_are_company_scoped(self):
        _, other_project, _, _ = self.create_other_company()
        listing = self.client.get(reverse('project-list'))
        detail = self.client.get(reverse('project-detail', args=(other_project.pk,)))
        update = self.client.patch(
            reverse('project-detail', args=(other_project.pk,)),
            {'name': 'Attempted update'},
        )
        delete = self.client.delete(reverse('project-detail', args=(other_project.pk,)))

        self.assertEqual([item['id'] for item in listing.data], [self.project.pk])
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete.status_code, status.HTTP_404_NOT_FOUND)

    def test_requirement_nested_crud_and_defaults(self):
        list_url = reverse('project-requirement-list', args=(self.project.pk,))
        create = self.client.post(
            list_url,
            {
                'requirement': 'Deliver the first release',
                'required_skills': 'Python, Django',
                'required_roles': 'Backend engineer',
                'deadline': '2026-12-01',
            },
        )
        requirement_id = create.data['id']
        detail_url = reverse(
            'project-requirement-detail',
            args=(self.project.pk, requirement_id),
        )
        listing = self.client.get(list_url)
        retrieve = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'priority': 'high'})
        delete = self.client.delete(detail_url)

        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create.data['project'], self.project.pk)
        self.assertEqual(create.data['priority'], 'medium')
        self.assertEqual(create.data['required_roles'], 'Backend engineer')
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['priority'], 'high')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)

    def test_requirement_requires_text_and_cannot_be_reparented(self):
        create = self.client.post(
            reverse('project-requirement-list', args=(self.project.pk,)),
            {},
        )
        requirement = ProjectRequirement.objects.create(
            project=self.project,
            requirement='Existing requirement',
        )
        update = self.client.patch(
            reverse(
                'project-requirement-detail',
                args=(self.project.pk, requirement.pk),
            ),
            {'project': 99999},
        )

        self.assertEqual(create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('requirement', create.data)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['project'], self.project.pk)

    def test_project_member_crud_for_employee_and_agent(self):
        list_url = reverse('project-member-list', args=(self.project.pk,))
        employee_create = self.client.post(
            list_url,
            {
                'employee': self.employee.pk,
                'member_type': 'employee',
                'role': 'Developer',
            },
        )
        employee_id = employee_create.data['id']
        detail_url = reverse(
            'project-member-detail',
            args=(self.project.pk, employee_id),
        )
        agent_create = self.client.post(
            list_url,
            {
                'ai_agent': self.agent.pk,
                'member_type': 'ai_agent',
            },
        )
        listing = self.client.get(list_url)
        retrieve = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'status': 'inactive'})
        delete = self.client.delete(detail_url)

        self.assertEqual(employee_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(employee_create.data['project'], self.project.pk)
        self.assertEqual(employee_create.data['employee'], self.employee.pk)
        self.assertIsNone(employee_create.data['ai_agent'])
        self.assertEqual(employee_create.data['status'], 'active')
        self.assertTrue(employee_create.data['assigned_at'])
        self.assertEqual(agent_create.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(agent_create.data['employee'])
        self.assertEqual(agent_create.data['ai_agent'], self.agent.pk)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['status'], 'inactive')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)

    def test_project_member_requires_exactly_one_candidate(self):
        url = reverse('project-member-list', args=(self.project.pk,))
        neither = self.client.post(url, {'member_type': 'employee'})
        both = self.client.post(
            url,
            {
                'employee': self.employee.pk,
                'ai_agent': self.agent.pk,
                'member_type': 'both',
            },
        )

        self.assertEqual(neither.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(both.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ProjectMember.objects.count(), 0)

    def test_database_enforces_exactly_one_candidate(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectMember.objects.create(project=self.project, member_type='none')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectMember.objects.create(
                project=self.project,
                employee=self.employee,
                ai_agent=self.agent,
                member_type='both',
            )

    def test_project_member_rejects_cross_company_employee_and_agent(self):
        _, _, other_employee, other_agent = self.create_other_company()
        url = reverse('project-member-list', args=(self.project.pk,))
        employee_response = self.client.post(
            url,
            {'employee': other_employee.pk, 'member_type': 'employee'},
        )
        agent_response = self.client.post(
            url,
            {'ai_agent': other_agent.pk, 'member_type': 'ai_agent'},
        )

        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(agent_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ProjectMember.objects.count(), 0)

    def test_admin_project_member_form_preserves_candidate_and_company_rules(self):
        _, _, other_employee, _ = self.create_other_company()
        conflicting_candidates = ProjectMemberAdminForm(
            data={
                'project': self.project.pk,
                'employee': self.employee.pk,
                'ai_agent': self.agent.pk,
                'role': '',
                'member_type': 'employee',
                'status': 'active',
            },
        )
        cross_company_candidate = ProjectMemberAdminForm(
            data={
                'project': self.project.pk,
                'employee': other_employee.pk,
                'ai_agent': '',
                'role': '',
                'member_type': 'employee',
                'status': 'active',
            },
        )

        self.assertFalse(conflicting_candidates.is_valid())
        self.assertIn(
            'Exactly one of employee or AI agent must be selected.',
            conflicting_candidates.non_field_errors(),
        )
        self.assertFalse(cross_company_candidate.is_valid())
        self.assertIn(
            'The employee must belong to the project company.',
            cross_company_candidate.non_field_errors(),
        )

    def test_admin_project_form_prevents_moving_existing_members_between_companies(self):
        ProjectMember.objects.create(
            project=self.project,
            employee=self.employee,
            member_type='employee',
        )
        other_company, _, _, _ = self.create_other_company()
        form = ProjectAdminForm(
            data={
                'company': other_company.pk,
                'name': self.project.name,
                'description': '',
                'status': self.project.status,
                'priority': self.project.priority,
                'start_date': '',
                'deadline': '',
            },
            instance=self.project,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            'Moving this project would invalidate existing members.',
            form.non_field_errors(),
        )

    def test_nested_resources_are_scoped_to_accessible_parent_project(self):
        _, other_project, _, _ = self.create_other_company()
        requirement = ProjectRequirement.objects.create(
            project=other_project,
            requirement='Private requirement',
        )
        member = ProjectMember.objects.create(
            project=other_project,
            ai_agent=AIAgent.objects.get(company=other_project.company),
            member_type='ai_agent',
        )
        inaccessible_urls = (
            reverse('project-requirement-list', args=(other_project.pk,)),
            reverse(
                'project-requirement-detail',
                args=(other_project.pk, requirement.pk),
            ),
            reverse('project-member-list', args=(other_project.pk,)),
            reverse(
                'project-member-detail',
                args=(other_project.pk, member.pk),
            ),
        )

        for url in inaccessible_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nested_cross_company_detail_update_and_delete_return_404(self):
        _, other_project, _, other_agent = self.create_other_company()
        requirement = ProjectRequirement.objects.create(
            project=other_project,
            requirement='Private requirement',
        )
        member = ProjectMember.objects.create(
            project=other_project,
            ai_agent=other_agent,
            member_type='ai_agent',
        )
        inaccessible_urls = (
            reverse(
                'project-requirement-detail',
                args=(other_project.pk, requirement.pk),
            ),
            reverse(
                'project-member-detail',
                args=(other_project.pk, member.pk),
            ),
        )

        for url in inaccessible_urls:
            with self.subTest(method='GET', url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
            with self.subTest(method='PATCH', url=url):
                self.assertEqual(
                    self.client.patch(url, {'status': 'changed'}).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
            with self.subTest(method='DELETE', url=url):
                self.assertEqual(
                    self.client.delete(url).status_code,
                    status.HTTP_404_NOT_FOUND,
                )

    def test_cross_company_nested_create_returns_404(self):
        _, other_project, _, _ = self.create_other_company()

        response = self.client.post(
            reverse('project-requirement-list', args=(other_project.pk,)),
            {'requirement': 'Unauthorized write'},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            ProjectRequirement.objects.filter(
                project=other_project,
                requirement='Unauthorized write',
            ).exists()
        )

    def test_member_role_can_read_but_cannot_write_project_resources(self):
        member_user = User.objects.create_user(
            username='project-member',
            email='project-member@example.com',
            password='Safe-project-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member_user,
            role=CompanyUser.Role.MEMBER,
        )
        requirement = ProjectRequirement.objects.create(
            project=self.project,
            requirement='Read-only requirement',
        )
        self.client.force_authenticate(member_user)

        project_read = self.client.get(reverse('project-detail', args=(self.project.pk,)))
        project_update = self.client.patch(
            reverse('project-detail', args=(self.project.pk,)),
            {'name': 'Forbidden'},
        )
        requirement_read = self.client.get(
            reverse(
                'project-requirement-detail',
                args=(self.project.pk, requirement.pk),
            )
        )
        requirement_create = self.client.post(
            reverse('project-requirement-list', args=(self.project.pk,)),
            {'requirement': 'Forbidden'},
        )

        self.assertEqual(project_read.status_code, status.HTTP_200_OK)
        self.assertEqual(project_update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(requirement_read.status_code, status.HTTP_200_OK)
        self.assertEqual(requirement_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_cannot_move_company_when_existing_member_would_be_invalid(self):
        second_company = Company.objects.create(
            created_by_user=User.objects.create_user(
                username='second-project-owner',
                email='second-project-owner@example.com',
                password='Safe-project-password-123!',
            ),
            name='Second authorized company',
        )
        CompanyUser.objects.create(
            company=second_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )
        ProjectMember.objects.create(
            project=self.project,
            employee=self.employee,
            member_type='employee',
        )

        response = self.client.patch(
            reverse('project-detail', args=(self.project.pk,)),
            {'company': second_company.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('company', response.data)

    def test_all_project_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        urls = (
            reverse('project-list'),
            reverse('project-detail', args=(self.project.pk,)),
            reverse('project-requirement-list', args=(self.project.pk,)),
            reverse('project-member-list', args=(self.project.pk,)),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_project_route_names_resolve(self):
        self.assertEqual(resolve('/api/v1/projects/').url_name, 'project-list')
        self.assertEqual(
            resolve(f'/api/v1/projects/{self.project.pk}/').url_name,
            'project-detail',
        )
        self.assertEqual(
            resolve(f'/api/v1/projects/{self.project.pk}/requirements/').url_name,
            'project-requirement-list',
        )
        self.assertEqual(
            resolve(f'/api/v1/projects/{self.project.pk}/members/').url_name,
            'project-member-list',
        )
