from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from companies.models import Company, CompanyUser
from .models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill


User = get_user_model()


class WorkforceApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='workforce-owner',
            email='workforce-owner@example.com',
            password='Safe-workforce-password-123!',
        )
        self.company = self.create_company(self.owner, 'Owner company')
        self.client.force_authenticate(self.owner)
        self.department = Department.objects.create(
            company=self.company,
            name='Engineering',
        )
        self.employee = Employee.objects.create(
            department=self.department,
            employee_code='EMP-001',
            first_name='Alex',
            last_name='Smith',
        )
        self.skill = Skill.objects.create(company=self.company, name='Python')
        self.employee_skill = EmployeeSkill.objects.create(
            employee=self.employee,
            skill=self.skill,
        )

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
            username='other-owner',
            email='other-owner@example.com',
            password='Safe-workforce-password-123!',
        )
        company = self.create_company(user, 'Other company')
        department = Department.objects.create(company=company, name='Other dept')
        employee = Employee.objects.create(
            department=department,
            employee_code='OTHER-001',
            first_name='Taylor',
            last_name='Jones',
        )
        skill = Skill.objects.create(company=company, name='Other skill')
        return company, department, employee, skill

    def test_department_crud(self):
        create_response = self.client.post(
            reverse('department-list'),
            {'company': self.company.pk, 'name': 'Research', 'description': 'R&D'},
        )
        department_id = create_response.data['id']
        detail_url = reverse('department-detail', args=(department_id,))

        read_response = self.client.get(detail_url)
        list_response = self.client.get(reverse('department-list'))
        update_response = self.client.patch(detail_url, {'name': 'Applied Research'})
        delete_response = self.client.delete(detail_url)

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_employee_crud_and_optional_email(self):
        data = {
            'department': self.department.pk,
            'employee_code': 'EMP-002',
            'first_name': 'Sam',
            'last_name': 'Worker',
        }
        create_response = self.client.post(reverse('employee-list'), data)
        employee_id = create_response.data['id']
        detail_url = reverse('employee-detail', args=(employee_id,))

        read_response = self.client.get(detail_url)
        list_response = self.client.get(reverse('employee-list'))
        update_response = self.client.patch(detail_url, {'phone': '555-0102'})
        delete_response = self.client.delete(detail_url)

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(create_response.data['email'])
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_employee_ai_profile_nested_crud_and_defaults(self):
        profile_url = reverse('employee-profile', args=(self.employee.pk,))
        create_response = self.client.post(profile_url, {'job_title': 'Engineer'})
        read_response = self.client.get(profile_url)
        update_response = self.client.patch(
            profile_url,
            {'availability_status': EmployeeAIProfile.AvailabilityStatus.UNAVAILABLE},
        )
        delete_response = self.client.delete(profile_url)

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['experience_years'], '0.00')
        self.assertEqual(create_response.data['current_workload'], '0.00')
        self.assertEqual(create_response.data['employment_status'], 'active')
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_skill_crud(self):
        create_response = self.client.post(
            reverse('skill-list'),
            {'company': self.company.pk, 'name': 'Django', 'category': 'backend'},
        )
        skill_id = create_response.data['id']
        detail_url = reverse('skill-detail', args=(skill_id,))

        read_response = self.client.get(detail_url)
        list_response = self.client.get(reverse('skill-list'))
        update_response = self.client.patch(detail_url, {'category': 'web'})
        delete_response = self.client.delete(detail_url)

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_employee_skill_crud(self):
        response = self.client.post(
            reverse('employee-skill-list'),
            {
                'employee': self.employee.pk,
                'skill': self.skill.pk,
                'proficiency': '80.50',
                'years_experience': '3.00',
            },
        )
        # The setup assignment already exists, so duplicate insertion is rejected.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.employee_skill.delete()
        response = self.client.post(
            reverse('employee-skill-list'),
            {'employee': self.employee.pk, 'skill': self.skill.pk},
        )
        assignment_id = response.data['id']
        detail_url = reverse('employee-skill-detail', args=(assignment_id,))
        read_response = self.client.get(detail_url)
        list_response = self.client.get(reverse('employee-skill-list'))
        update_response = self.client.patch(detail_url, {'proficiency': '95.00'})
        delete_response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['years_experience'], '0.00')
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_duplicate_employee_code_within_department_is_rejected(self):
        response = self.client.post(
            reverse('employee-list'),
            {
                'department': self.department.pk,
                'employee_code': self.employee.employee_code,
                'first_name': 'Duplicate',
                'last_name': 'Code',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_skill_name_within_company_is_rejected(self):
        response = self.client.post(
            reverse('skill-list'),
            {'company': self.company.pk, 'name': self.skill.name},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_profile_and_employee_skill_are_prevented(self):
        profile_url = reverse('employee-profile', args=(self.employee.pk,))
        self.assertEqual(
            self.client.post(profile_url, {}).status_code,
            status.HTTP_201_CREATED,
        )
        duplicate_profile = self.client.post(profile_url, {})
        self.assertEqual(duplicate_profile.status_code, status.HTTP_409_CONFLICT)

        duplicate_assignment = self.client.post(
            reverse('employee-skill-list'),
            {'employee': self.employee.pk, 'skill': self.skill.pk},
        )
        self.assertEqual(duplicate_assignment.status_code, status.HTTP_400_BAD_REQUEST)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmployeeAIProfile.objects.create(employee=self.employee)

    def test_company_member_can_read_but_not_write_workforce_data(self):
        member = User.objects.create_user(
            username='read-only-member',
            email='read-only@example.com',
            password='Safe-workforce-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(member)

        list_response = self.client.get(reverse('department-list'))
        create_response = self.client.post(
            reverse('department-list'),
            {'company': self.company.pk, 'name': 'Blocked'},
        )
        update_response = self.client.patch(
            reverse('department-detail', args=(self.department.pk,)),
            {'name': 'Blocked'},
        )
        delete_response = self.client.delete(
            reverse('department-detail', args=(self.department.pk,)),
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_and_manager_can_create_workforce_records(self):
        for role in (CompanyUser.Role.ADMIN, CompanyUser.Role.MANAGER):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f'writer-{role}',
                    email=f'writer-{role}@example.com',
                    password='Safe-workforce-password-123!',
                )
                CompanyUser.objects.create(company=self.company, user=user, role=role)
                self.client.force_authenticate(user)

                response = self.client.post(
                    reverse('department-list'),
                    {'company': self.company.pk, 'name': f'{role} department'},
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_write_role_is_checked_for_the_specific_company(self):
        _, other_department, _, _ = self.create_other_company()
        manager = User.objects.create_user(
            username='other-manager',
            email='other-manager@example.com',
            password='Safe-workforce-password-123!',
        )
        CompanyUser.objects.create(
            company=other_department.company,
            user=manager,
            role=CompanyUser.Role.MANAGER,
        )
        CompanyUser.objects.create(
            company=self.company,
            user=manager,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(manager)

        response = self.client.patch(
            reverse('department-detail', args=(self.department.pk,)),
            {'name': 'Unauthorized'},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.department.refresh_from_db()
        self.assertEqual(self.department.name, 'Engineering')

    def test_cross_company_objects_are_hidden_on_reads_updates_and_deletes(self):
        _, department, employee, skill = self.create_other_company()
        other_profile = EmployeeAIProfile.objects.create(employee=employee)
        other_assignment = EmployeeSkill.objects.create(employee=employee, skill=skill)
        self.assertEqual(
            [item['id'] for item in self.client.get(reverse('department-list')).data],
            [self.department.pk],
        )
        self.assertEqual(
            [item['id'] for item in self.client.get(reverse('employee-list')).data],
            [self.employee.pk],
        )
        self.assertEqual(
            [item['id'] for item in self.client.get(reverse('skill-list')).data],
            [self.skill.pk],
        )
        self.assertEqual(
            [
                item['id']
                for item in self.client.get(reverse('employee-skill-list')).data
            ],
            [self.employee_skill.pk],
        )
        paths = (
            ('department-detail', department.pk),
            ('employee-detail', employee.pk),
            ('skill-detail', skill.pk),
        )
        for route_name, object_id in paths:
            with self.subTest(route=route_name):
                url = reverse(route_name, args=(object_id,))
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(
                    self.client.patch(url, {'name': 'Intrusion'}).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)

        self.assertEqual(
            self.client.get(reverse('employee-profile', args=(employee.pk,))).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        profile_url = reverse('employee-profile', args=(employee.pk,))
        self.assertEqual(
            self.client.patch(profile_url, {'job_title': 'Intrusion'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(profile_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        assignment_url = reverse('employee-skill-detail', args=(other_assignment.pk,))
        self.assertEqual(self.client.get(assignment_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(assignment_url, {'proficiency': '1.00'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(assignment_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(EmployeeAIProfile.objects.filter(pk=other_profile.pk).exists())

    def test_cross_company_foreign_keys_and_employee_skill_links_are_rejected(self):
        _, other_department, other_employee, other_skill = self.create_other_company()
        employee_create = self.client.post(
            reverse('employee-list'),
            {
                'department': other_department.pk,
                'employee_code': 'BLOCKED',
                'first_name': 'No',
                'last_name': 'Access',
            },
        )
        skill_create = self.client.post(
            reverse('skill-list'),
            {'company': other_department.company_id, 'name': 'Blocked'},
        )
        mismatch_assignment = self.client.post(
            reverse('employee-skill-list'),
            {'employee': self.employee.pk, 'skill': other_skill.pk},
        )
        unauthorized_employee_assignment = self.client.post(
            reverse('employee-skill-list'),
            {'employee': other_employee.pk, 'skill': self.skill.pk},
        )

        self.assertEqual(employee_create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(skill_create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch_assignment.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            unauthorized_employee_assignment.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Department.objects.count(), 2)
        self.assertEqual(Employee.objects.count(), 2)
        self.assertEqual(Skill.objects.count(), 2)

    def test_updates_cannot_break_existing_same_company_skill_links(self):
        other_company, other_department, _, _ = self.create_other_company()
        CompanyUser.objects.create(
            company=other_company,
            user=self.owner,
            role=CompanyUser.Role.OWNER,
        )

        department_response = self.client.patch(
            reverse('department-detail', args=(self.department.pk,)),
            {'company': other_company.pk},
        )
        employee_response = self.client.patch(
            reverse('employee-detail', args=(self.employee.pk,)),
            {'department': other_department.pk},
        )
        skill_response = self.client.patch(
            reverse('skill-detail', args=(self.skill.pk,)),
            {'company': other_company.pk},
        )

        self.assertEqual(department_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(skill_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.employee_skill.refresh_from_db()
        self.assertEqual(self.employee_skill.employee.department.company_id, self.company.pk)
        self.assertEqual(self.employee_skill.skill.company_id, self.company.pk)

    def test_duplicate_constraints_are_enforced_in_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(
                    department=self.department,
                    employee_code=self.employee.employee_code,
                    first_name='Duplicate',
                    last_name='Employee',
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Skill.objects.create(company=self.company, name=self.skill.name)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmployeeSkill.objects.create(employee=self.employee, skill=self.skill)

    def test_required_fields_and_invalid_profile_choices_are_rejected(self):
        department_response = self.client.post(
            reverse('department-list'),
            {'company': self.company.pk},
        )
        employee_response = self.client.post(
            reverse('employee-list'),
            {'department': self.department.pk, 'employee_code': 'MISSING-NAME'},
        )
        profile_response = self.client.post(
            reverse('employee-profile', args=(self.employee.pk,)),
            {'employment_status': 'not-a-status'},
        )

        self.assertEqual(department_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', department_response.data)
        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(profile_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_all_workforce_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        requests = (
            ('get', reverse('department-list'), None),
            ('post', reverse('department-list'), {'company': self.company.pk, 'name': 'X'}),
            ('get', reverse('employee-list'), None),
            ('get', reverse('employee-detail', args=(self.employee.pk,)), None),
            ('get', reverse('employee-profile', args=(self.employee.pk,)), None),
            ('get', reverse('skill-list'), None),
            ('get', reverse('employee-skill-list'), None),
        )
        for method, url, data in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_workforce_routes_resolve(self):
        paths = (
            '/api/v1/workforce/departments/',
            '/api/v1/workforce/departments/1/',
            '/api/v1/workforce/employees/',
            '/api/v1/workforce/employees/1/',
            '/api/v1/workforce/employees/1/profile/',
            '/api/v1/workforce/skills/',
            '/api/v1/workforce/skills/1/',
            '/api/v1/workforce/employee-skills/',
            '/api/v1/workforce/employee-skills/1/',
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(resolve(path).url_name.startswith(
                    ('department-', 'employee-', 'skill-')
                ))
