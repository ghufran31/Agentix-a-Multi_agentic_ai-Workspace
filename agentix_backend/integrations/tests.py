from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from companies.models import Company, CompanyUser
from .models import Connection


User = get_user_model()


class ConnectionApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='connection-owner',
            email='connection-owner@example.com',
            password='Safe-connection-password-123!',
        )
        self.company = self.create_company(self.owner, 'Connected company')
        self.connection = Connection.objects.create(
            company=self.company,
            provider='Example Cloud',
            account_name='Production',
        )
        self.client.force_authenticate(self.owner)
        self.list_url = reverse('connection-list')

    def create_company(self, user, name):
        company = Company.objects.create(created_by_user=user, name=name)
        CompanyUser.objects.create(
            company=company,
            user=user,
            role=CompanyUser.Role.OWNER,
        )
        return company

    def create_other_company_and_connection(self):
        user = User.objects.create_user(
            username='other-connection-owner',
            email='other-connection-owner@example.com',
            password='Safe-connection-password-123!',
        )
        company = self.create_company(user, 'Other company')
        connection = Connection.objects.create(
            company=company,
            provider='Private Provider',
            account_name='Private account',
        )
        return company, connection

    def test_create_connection_metadata_and_default_status(self):
        response = self.client.post(
            self.list_url,
            {
                'company': self.company.pk,
                'provider': 'GitHub',
                'connection_type': 'repository',
                'account_name': 'Agentix',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'disconnected')
        self.assertIsNone(response.data['connected_at'])
        self.assertEqual(response.data['provider'], 'GitHub')
        self.assertNotIn('credentials', response.data)
        self.assertNotIn('token', response.data)

    def test_provider_is_required_and_optional_fields_may_be_null(self):
        missing_provider = self.client.post(
            self.list_url,
            {'company': self.company.pk},
        )
        minimal = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'provider': 'Example'},
        )

        self.assertEqual(missing_provider.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('provider', missing_provider.data)
        self.assertEqual(minimal.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(minimal.data['connection_type'])
        self.assertIsNone(minimal.data['account_name'])
        self.assertIsNone(minimal.data['connected_at'])

    def test_list_returns_only_connections_for_member_companies(self):
        self.create_other_company_and_connection()

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [self.connection.pk])

    def test_retrieve_update_and_delete_connection(self):
        detail_url = reverse('connection-detail', args=(self.connection.pk,))
        retrieve = self.client.get(detail_url)
        update = self.client.patch(
            detail_url,
            {
                'account_name': 'Updated account',
                'status': 'connected',
                'connected_at': '2026-10-19T12:00:00Z',
            },
        )
        delete = self.client.delete(detail_url)

        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['account_name'], 'Updated account')
        self.assertEqual(update.data['status'], 'connected')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Connection.objects.filter(pk=self.connection.pk).exists())

    def test_member_can_read_but_cannot_create_update_or_delete(self):
        member = User.objects.create_user(
            username='connection-member',
            email='connection-member@example.com',
            password='Safe-connection-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(member)
        detail_url = reverse('connection-detail', args=(self.connection.pk,))

        read = self.client.get(detail_url)
        create = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'provider': 'Forbidden'},
        )
        update = self.client.patch(detail_url, {'status': 'connected'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_create_and_update_connection(self):
        manager = User.objects.create_user(
            username='connection-manager',
            email='connection-manager@example.com',
            password='Safe-connection-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=manager,
            role=CompanyUser.Role.MANAGER,
        )
        self.client.force_authenticate(manager)

        create = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'provider': 'Manager Provider'},
        )
        update = self.client.patch(
            reverse('connection-detail', args=(self.connection.pk,)),
            {'status': 'pending'},
        )

        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(update.status_code, status.HTTP_200_OK)

    def test_unauthorized_company_ids_are_rejected_on_create_and_update(self):
        other_company, _ = self.create_other_company_and_connection()
        create = self.client.post(
            self.list_url,
            {'company': other_company.pk, 'provider': 'Unauthorized'},
        )
        update = self.client.patch(
            reverse('connection-detail', args=(self.connection.pk,)),
            {'company': other_company.pk},
        )
        nonexistent = self.client.post(
            self.list_url,
            {'company': 999999, 'provider': 'Unknown'},
        )

        self.assertEqual(create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(update.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(nonexistent.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_company_connections_return_404_for_all_detail_operations(self):
        _, other_connection = self.create_other_company_and_connection()
        detail_url = reverse('connection-detail', args=(other_connection.pk,))

        read = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'status': 'connected'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Connection.objects.filter(pk=other_connection.pk).exists())

    def test_non_writer_cannot_probe_another_company_connection(self):
        member = User.objects.create_user(
            username='reader-only-connection',
            email='reader-only@example.com',
            password='Safe-connection-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        _, other_connection = self.create_other_company_and_connection()
        self.client.force_authenticate(member)

        response = self.client.patch(
            reverse('connection-detail', args=(other_connection.pk,)),
            {'status': 'connected'},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_every_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        detail_url = reverse('connection-detail', args=(self.connection.pk,))
        responses = (
            self.client.get(self.list_url),
            self.client.post(self.list_url, {'company': self.company.pk, 'provider': 'No auth'}),
            self.client.get(detail_url),
            self.client.patch(detail_url, {'status': 'connected'}),
            self.client.delete(detail_url),
        )

        self.assertTrue(
            all(response.status_code == status.HTTP_401_UNAUTHORIZED for response in responses)
        )

    def test_connection_routes_resolve(self):
        self.assertEqual(resolve('/api/v1/integrations/').url_name, 'connection-list')
        self.assertEqual(
            resolve('/api/v1/integrations/1/').url_name,
            'connection-detail',
        )
