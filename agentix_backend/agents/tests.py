from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from companies.models import Company, CompanyUser
from .models import AIAgent


User = get_user_model()


class AIAgentApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='agent-owner',
            email='agent-owner@example.com',
            password='Safe-agent-password-123!',
        )
        self.company = self.create_company(self.owner, 'Agent company')
        self.agent = AIAgent.objects.create(
            company=self.company,
            name='Planning assistant',
            agent_type='planner',
        )
        self.client.force_authenticate(self.owner)
        self.list_url = reverse('ai-agent-list')

    def create_company(self, user, name):
        company = Company.objects.create(created_by_user=user, name=name)
        CompanyUser.objects.create(
            company=company,
            user=user,
            role=CompanyUser.Role.OWNER,
        )
        return company

    def create_other_company_and_agent(self):
        user = User.objects.create_user(
            username='other-agent-owner',
            email='other-agent-owner@example.com',
            password='Safe-agent-password-123!',
        )
        company = self.create_company(user, 'Other company')
        agent = AIAgent.objects.create(
            company=company,
            name='Private agent',
        )
        return company, agent

    def test_create_agent_metadata_and_default_status(self):
        response = self.client.post(
            self.list_url,
            {
                'company': self.company.pk,
                'name': 'Research assistant',
                'agent_type': 'research',
                'description': 'Metadata only',
                'capabilities': 'Summarization; classification',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'active')
        self.assertTrue(response.data['created_at'])
        self.assertEqual(response.data['name'], 'Research assistant')
        self.assertNotIn('credentials', response.data)
        self.assertNotIn('api_key', response.data)

    def test_name_is_required_and_optional_fields_default_to_null(self):
        missing_name = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'agent_type': 'assistant'},
        )
        minimal = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'name': 'Minimal agent'},
        )

        self.assertEqual(missing_name.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', missing_name.data)
        self.assertEqual(minimal.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(minimal.data['agent_type'])
        self.assertIsNone(minimal.data['description'])
        self.assertIsNone(minimal.data['capabilities'])
        self.assertEqual(minimal.data['status'], 'active')

    def test_maximum_field_lengths_are_validated(self):
        response = self.client.post(
            self.list_url,
            {
                'company': self.company.pk,
                'name': 'n' * 151,
                'agent_type': 't' * 101,
                'status': 's' * 51,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)
        self.assertIn('agent_type', response.data)
        self.assertIn('status', response.data)

    def test_list_returns_only_agents_for_member_companies(self):
        self.create_other_company_and_agent()

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [self.agent.pk])

    def test_retrieve_update_and_delete_agent(self):
        detail_url = reverse('ai-agent-detail', args=(self.agent.pk,))
        retrieve = self.client.get(detail_url)
        update = self.client.patch(
            detail_url,
            {
                'name': 'Updated assistant',
                'status': 'paused',
                'capabilities': 'Updated metadata',
            },
        )
        delete = self.client.delete(detail_url)

        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['name'], 'Updated assistant')
        self.assertEqual(update.data['status'], 'paused')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AIAgent.objects.filter(pk=self.agent.pk).exists())

    def test_accessible_agent_can_move_to_another_authorized_company(self):
        second_company = Company.objects.create(
            created_by_user=User.objects.create_user(
                username='second-agent-owner',
                email='second-agent-owner@example.com',
                password='Safe-agent-password-123!',
            ),
            name='Second company',
        )
        CompanyUser.objects.create(
            company=second_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )

        response = self.client.patch(
            reverse('ai-agent-detail', args=(self.agent.pk,)),
            {'company': second_company.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company'], second_company.pk)

    def test_member_can_read_but_cannot_create_update_or_delete(self):
        member = User.objects.create_user(
            username='agent-member',
            email='agent-member@example.com',
            password='Safe-agent-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(member)
        detail_url = reverse('ai-agent-detail', args=(self.agent.pk,))

        read = self.client.get(detail_url)
        create = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'name': 'Forbidden'},
        )
        update = self.client.patch(detail_url, {'status': 'paused'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_and_manager_can_write_agents(self):
        for role in (CompanyUser.Role.ADMIN, CompanyUser.Role.MANAGER):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f'agent-writer-{role}',
                    email=f'agent-writer-{role}@example.com',
                    password='Safe-agent-password-123!',
                )
                CompanyUser.objects.create(company=self.company, user=user, role=role)
                self.client.force_authenticate(user)

                response = self.client.post(
                    self.list_url,
                    {'company': self.company.pk, 'name': f'{role} agent'},
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_writer_role_in_another_company_does_not_authorize_writes_here(self):
        other_company, _ = self.create_other_company_and_agent()
        user = User.objects.create_user(
            username='mixed-role-agent-user',
            email='mixed-role-agent-user@example.com',
            password='Safe-agent-password-123!',
        )
        CompanyUser.objects.create(
            company=other_company,
            user=user,
            role=CompanyUser.Role.MANAGER,
        )
        CompanyUser.objects.create(
            company=self.company,
            user=user,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(user)

        update = self.client.patch(
            reverse('ai-agent-detail', args=(self.agent.pk,)),
            {'status': 'paused'},
        )
        create = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'name': 'Not authorized'},
        )

        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(create.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthorized_company_ids_are_rejected_on_create_and_update(self):
        other_company, _ = self.create_other_company_and_agent()
        create = self.client.post(
            self.list_url,
            {'company': other_company.pk, 'name': 'Unauthorized'},
        )
        update = self.client.patch(
            reverse('ai-agent-detail', args=(self.agent.pk,)),
            {'company': other_company.pk},
        )
        nonexistent = self.client.post(
            self.list_url,
            {'company': 999999, 'name': 'Unknown'},
        )

        self.assertEqual(create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(update.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(nonexistent.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_company_agents_return_404_for_read_update_and_delete(self):
        _, other_agent = self.create_other_company_and_agent()
        detail_url = reverse('ai-agent-detail', args=(other_agent.pk,))

        read = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'status': 'paused'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(AIAgent.objects.filter(pk=other_agent.pk).exists())

    def test_every_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        detail_url = reverse('ai-agent-detail', args=(self.agent.pk,))
        responses = (
            self.client.get(self.list_url),
            self.client.post(self.list_url, {'company': self.company.pk, 'name': 'No auth'}),
            self.client.get(detail_url),
            self.client.patch(detail_url, {'status': 'paused'}),
            self.client.delete(detail_url),
        )

        self.assertTrue(
            all(response.status_code == status.HTTP_401_UNAUTHORIZED for response in responses)
        )

    def test_agent_routes_resolve(self):
        self.assertEqual(resolve('/api/v1/agents/').url_name, 'ai-agent-list')
        self.assertEqual(
            resolve('/api/v1/agents/1/').url_name,
            'ai-agent-detail',
        )
