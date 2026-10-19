from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse, resolve
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Company, CompanyUser


User = get_user_model()


class CompaniesApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='Safe-test-password-198!',
        )
        self.other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='Safe-test-password-198!',
        )
        self.company_data = {
            'name': 'Agentix Labs',
            'industry': 'Software',
            'description': 'A project workspace.',
            'email': 'contact@example.com',
            'phone': '+1-555-0100',
            'address': '1 Example Street',
        }
        self.list_url = reverse('company-list-create')
        self.client.force_authenticate(self.owner)

    def create_company(self, *, creator=None, name='Test Company'):
        creator = creator or self.owner
        company = Company.objects.create(
            created_by_user=creator,
            name=name,
        )
        CompanyUser.objects.create(
            company=company,
            user=creator,
            role=CompanyUser.Role.OWNER,
        )
        return company

    def test_create_company_creates_owner_membership_atomically(self):
        response = self.client.post(self.list_url, self.company_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(pk=response.data['id'])
        membership = CompanyUser.objects.get(company=company, user=self.owner)
        self.assertEqual(company.created_by_user, self.owner)
        self.assertEqual(membership.role, CompanyUser.Role.OWNER)
        self.assertEqual(response.data['name'], 'Agentix Labs')
        self.assertNotIn('password', response.data)

    def test_list_and_retrieve_only_companies_the_user_belongs_to(self):
        own_company = self.create_company()
        self.create_company(creator=self.other_user, name='Other Company')

        response = self.client.get(self.list_url)
        detail_response = self.client.get(
            reverse('company-detail', args=(own_company.pk,)),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [own_company.pk])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['name'], 'Test Company')

    def test_unauthorized_user_cannot_access_company_details_or_members(self):
        company = self.create_company()

        self.client.force_authenticate(self.other_user)
        detail_response = self.client.get(
            reverse('company-detail', args=(company.pk,)),
        )
        members_response = self.client.get(
            reverse('company-members', args=(company.pk,)),
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(members_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_members_endpoint_returns_only_safe_member_fields(self):
        company = self.create_company()

        response = self.client.get(
            reverse('company-members', args=(company.pk,)),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['role'], CompanyUser.Role.OWNER)
        self.assertEqual(response.data[0]['user']['username'], 'owner')
        self.assertNotIn('password', response.data[0]['user'])

    def test_only_owner_can_patch_company_details(self):
        company = self.create_company()
        update_url = reverse('company-detail', args=(company.pk,))
        owner_response = self.client.patch(update_url, {'name': 'Updated'})
        self.assertEqual(owner_response.status_code, status.HTTP_200_OK)

        for role in (
            CompanyUser.Role.ADMIN,
            CompanyUser.Role.MANAGER,
            CompanyUser.Role.MEMBER,
        ):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=role,
                    email=f'{role}@example.com',
                    password='Safe-test-password-198!',
                )
                CompanyUser.objects.create(company=company, user=user, role=role)
                self.client.force_authenticate(user)

                response = self.client.patch(update_url, {'name': f'{role} edit'})

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                company.refresh_from_db()
                self.assertEqual(company.name, 'Updated')

    def test_creator_cannot_create_a_second_company(self):
        self.create_company()

        response = self.client.post(self.list_url, self.company_data)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Company.objects.filter(created_by_user=self.owner).count(), 1)

    def test_duplicate_company_membership_is_rejected_by_database_constraint(self):
        company = self.create_company()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CompanyUser.objects.create(
                    company=company,
                    user=self.owner,
                    role=CompanyUser.Role.OWNER,
                )

        self.assertEqual(CompanyUser.objects.filter(company=company).count(), 1)

    def test_all_company_endpoints_require_authentication(self):
        company = self.create_company()
        self.client.force_authenticate(user=None)
        requests = (
            ('get', self.list_url, None),
            ('post', self.list_url, self.company_data),
            ('get', reverse('company-detail', args=(company.pk,)), None),
            ('patch', reverse('company-detail', args=(company.pk,)), {'name': 'Nope'}),
            ('get', reverse('company-members', args=(company.pk,)), None),
        )

        for method, url, data in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_company_creation_validates_required_name_and_email(self):
        missing_name = self.client.post(self.list_url, {'email': 'ok@example.com'})
        invalid_email = self.client.post(
            self.list_url,
            {'name': 'Invalid email company', 'email': 'not-an-email'},
        )

        self.assertEqual(missing_name.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', missing_name.data)
        self.assertEqual(invalid_email.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', invalid_email.data)
        self.assertEqual(Company.objects.count(), 0)

    def test_owner_membership_failure_rolls_back_company_creation(self):
        with patch(
            'companies.views.CompanyUser.objects.create',
            side_effect=IntegrityError('simulated membership constraint failure'),
        ):
            response = self.client.post(self.list_url, self.company_data)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Company.objects.filter(created_by_user=self.owner).count(), 0)
        self.assertEqual(CompanyUser.objects.filter(user=self.owner).count(), 0)

    def test_company_routes_resolve(self):
        expected = {
            '/api/v1/companies/': 'company-list-create',
            '/api/v1/companies/1/': 'company-detail',
            '/api/v1/companies/1/members/': 'company-members',
        }

        for path, name in expected.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).url_name, name)
