from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agents.models import AIAgent
from companies.models import Company, CompanyUser
from projects.models import Project
from workforce.models import Department, Employee
from .models import Recommendation


User = get_user_model()


class RecommendationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='recommendation-owner',
            email='recommendation-owner@example.com',
            password='Safe-recommendation-password-123!',
        )
        self.company = self.create_company(self.owner, 'Recommendation company')
        self.project = Project.objects.create(
            company=self.company,
            name='Recommendation project',
        )
        department = Department.objects.create(
            company=self.company,
            name='Engineering',
        )
        self.employee = Employee.objects.create(
            department=department,
            employee_code='REC-001',
            first_name='Avery',
            last_name='Employee',
        )
        self.agent = AIAgent.objects.create(
            company=self.company,
            name='Recommendation agent',
        )
        self.recommendation = Recommendation.objects.create(
            project=self.project,
            employee=self.employee,
            score='0.87500',
            rank=1,
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

    def create_other_company_records(self):
        user = User.objects.create_user(
            username='other-recommendation-owner',
            email='other-recommendation-owner@example.com',
            password='Safe-recommendation-password-123!',
        )
        company = self.create_company(user, 'Other recommendation company')
        project = Project.objects.create(company=company, name='Private project')
        department = Department.objects.create(company=company, name='Other dept')
        employee = Employee.objects.create(
            department=department,
            employee_code='OTHER-REC-001',
            first_name='Taylor',
            last_name='Employee',
        )
        agent = AIAgent.objects.create(company=company, name='Private agent')
        recommendation = Recommendation.objects.create(
            project=project,
            ai_agent=agent,
            score='0.50000',
            rank=2,
        )
        return company, project, employee, agent, recommendation

    def test_create_employee_or_agent_recommendation_and_defaults(self):
        list_url = reverse('recommendation-list')
        employee_create = self.client.post(
            list_url,
            {
                'project': self.project.pk,
                'employee': self.employee.pk,
                'recommended_role': 'Backend engineer',
                'score': '0.92345',
                'rank': 1,
                'reason': 'Relevant experience',
            },
        )
        agent_create = self.client.post(
            list_url,
            {
                'project': self.project.pk,
                'ai_agent': self.agent.pk,
                'score': '0.81234',
                'rank': 2,
            },
        )

        self.assertEqual(employee_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(employee_create.data['employee'], self.employee.pk)
        self.assertIsNone(employee_create.data['ai_agent'])
        self.assertEqual(employee_create.data['score'], '0.92345')
        self.assertEqual(employee_create.data['status'], 'pending')
        self.assertTrue(employee_create.data['created_at'])
        self.assertEqual(agent_create.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(agent_create.data['employee'])
        self.assertEqual(agent_create.data['ai_agent'], self.agent.pk)

    def test_score_rank_project_and_one_candidate_are_required(self):
        list_url = reverse('recommendation-list')
        missing_score_rank = self.client.post(
            list_url,
            {'project': self.project.pk, 'employee': self.employee.pk},
        )
        missing_candidate = self.client.post(
            list_url,
            {'project': self.project.pk, 'score': '0.12345', 'rank': 1},
        )
        conflicting_candidates = self.client.post(
            list_url,
            {
                'project': self.project.pk,
                'employee': self.employee.pk,
                'ai_agent': self.agent.pk,
                'score': '0.12345',
                'rank': 1,
            },
        )
        missing_project = self.client.post(
            list_url,
            {'employee': self.employee.pk, 'score': '0.12345', 'rank': 1},
        )

        self.assertEqual(missing_score_rank.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('score', missing_score_rank.data)
        self.assertIn('rank', missing_score_rank.data)
        self.assertEqual(missing_candidate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(conflicting_candidates.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_project.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', missing_project.data)

    def test_decimal_and_character_field_validation(self):
        response = self.client.post(
            reverse('recommendation-list'),
            {
                'project': self.project.pk,
                'employee': self.employee.pk,
                'recommended_role': 'r' * 151,
                'score': '1234.12345',
                'rank': 1,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('recommended_role', response.data)
        self.assertIn('score', response.data)

    def test_list_retrieve_update_and_delete(self):
        list_url = reverse('recommendation-list')
        detail_url = reverse(
            'recommendation-detail',
            args=(self.recommendation.pk,),
        )

        listing = self.client.get(list_url)
        retrieve = self.client.get(detail_url)
        update = self.client.patch(
            detail_url,
            {
                'score': '0.99999',
                'rank': 3,
                'status': 'accepted',
                'reason': 'Updated reason',
            },
        )
        delete = self.client.delete(detail_url)

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in listing.data], [self.recommendation.pk])
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['score'], '0.99999')
        self.assertEqual(update.data['rank'], 3)
        self.assertEqual(update.data['status'], 'accepted')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recommendation.objects.filter(pk=self.recommendation.pk).exists())

    def test_project_scoped_list_returns_only_that_projects_recommendations(self):
        other_project = Project.objects.create(
            company=self.company,
            name='Second project',
        )
        other_recommendation = Recommendation.objects.create(
            project=other_project,
            ai_agent=self.agent,
            score='0.70000',
            rank=1,
        )

        response = self.client.get(
            reverse('project-recommendation-list', args=(self.project.pk,))
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [self.recommendation.pk])
        self.assertNotIn(other_recommendation.pk, [item['id'] for item in response.data])

    def test_cross_company_project_and_recommendation_ids_are_hidden(self):
        _, other_project, _, _, other_recommendation = self.create_other_company_records()
        detail_url = reverse(
            'recommendation-detail',
            args=(other_recommendation.pk,),
        )
        retrieve = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'rank': 9})
        delete = self.client.delete(detail_url)
        nested = self.client.get(
            reverse('project-recommendation-list', args=(other_project.pk,))
        )

        self.assertEqual(retrieve.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(nested.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonmember_cannot_create_recommendation_for_project(self):
        _, other_project, _, _, _ = self.create_other_company_records()

        response = self.client.post(
            reverse('recommendation-list'),
            {
                'project': other_project.pk,
                'ai_agent': self.agent.pk,
                'score': '0.50000',
                'rank': 1,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', response.data)

    def test_cross_company_employee_and_agent_are_rejected(self):
        other_company, _, other_employee, other_agent, _ = (
            self.create_other_company_records()
        )
        CompanyUser.objects.create(
            company=other_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )
        list_url = reverse('recommendation-list')
        employee_response = self.client.post(
            list_url,
            {
                'project': self.project.pk,
                'employee': other_employee.pk,
                'score': '0.50000',
                'rank': 1,
            },
        )
        agent_response = self.client.post(
            list_url,
            {
                'project': self.project.pk,
                'ai_agent': other_agent.pk,
                'score': '0.50000',
                'rank': 1,
            },
        )

        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employee', employee_response.data)
        self.assertEqual(agent_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ai_agent', agent_response.data)

    def test_update_rejects_employee_or_agent_from_another_company(self):
        other_company, _, other_employee, other_agent, _ = (
            self.create_other_company_records()
        )
        CompanyUser.objects.create(
            company=other_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )
        employee_response = self.client.patch(
            reverse('recommendation-detail', args=(self.recommendation.pk,)),
            {'employee': other_employee.pk},
        )
        agent_recommendation = Recommendation.objects.create(
            project=self.project,
            ai_agent=self.agent,
            score='0.70000',
            rank=2,
        )
        agent_response = self.client.patch(
            reverse('recommendation-detail', args=(agent_recommendation.pk,)),
            {'ai_agent': other_agent.pk},
        )

        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employee', employee_response.data)
        self.assertEqual(agent_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ai_agent', agent_response.data)

    def test_cross_company_employee_or_agent_id_not_accessible_to_user_is_rejected(self):
        _, _, other_employee, other_agent, _ = self.create_other_company_records()

        employee_response = self.client.post(
            reverse('recommendation-list'),
            {
                'project': self.project.pk,
                'employee': other_employee.pk,
                'score': '0.50000',
                'rank': 1,
            },
        )
        agent_response = self.client.post(
            reverse('recommendation-list'),
            {
                'project': self.project.pk,
                'ai_agent': other_agent.pk,
                'score': '0.50000',
                'rank': 1,
            },
        )

        self.assertEqual(employee_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(agent_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_candidate_switch_preserves_exactly_one_target(self):
        detail_url = reverse(
            'recommendation-detail',
            args=(self.recommendation.pk,),
        )

        response = self.client.patch(
            detail_url,
            {'ai_agent': self.agent.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['employee'])
        self.assertEqual(response.data['ai_agent'], self.agent.pk)
        self.recommendation.refresh_from_db()
        self.assertIsNone(self.recommendation.employee_id)
        self.assertEqual(self.recommendation.ai_agent_id, self.agent.pk)

    def test_update_to_project_from_another_company_is_rejected(self):
        other_company, other_project, _, _, _ = self.create_other_company_records()
        CompanyUser.objects.create(
            company=other_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )

        response = self.client.patch(
            reverse('recommendation-detail', args=(self.recommendation.pk,)),
            {'project': other_project.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employee', response.data)

    def test_database_constraint_requires_exactly_one_candidate(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Recommendation.objects.create(
                project=self.project,
                score='0.50000',
                rank=1,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Recommendation.objects.create(
                project=self.project,
                employee=self.employee,
                ai_agent=self.agent,
                score='0.50000',
                rank=1,
            )

    def test_member_can_read_but_cannot_write_recommendations(self):
        member = User.objects.create_user(
            username='recommendation-member',
            email='recommendation-member@example.com',
            password='Safe-recommendation-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(member)
        detail_url = reverse(
            'recommendation-detail',
            args=(self.recommendation.pk,),
        )

        listing = self.client.get(reverse('recommendation-list'))
        retrieve = self.client.get(detail_url)
        create = self.client.post(
            reverse('recommendation-list'),
            {
                'project': self.project.pk,
                'employee': self.employee.pk,
                'score': '0.50000',
                'rank': 2,
            },
        )
        update = self.client.patch(detail_url, {'status': 'accepted'})
        delete = self.client.delete(detail_url)

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_and_manager_can_write_recommendations(self):
        for role in (CompanyUser.Role.ADMIN, CompanyUser.Role.MANAGER):
            with self.subTest(role=role):
                writer = User.objects.create_user(
                    username=f'recommendation-writer-{role}',
                    email=f'recommendation-writer-{role}@example.com',
                    password='Safe-recommendation-password-123!',
                )
                CompanyUser.objects.create(
                    company=self.company,
                    user=writer,
                    role=role,
                )
                self.client.force_authenticate(writer)

                response = self.client.post(
                    reverse('recommendation-list'),
                    {
                        'project': self.project.pk,
                        'employee': self.employee.pk,
                        'score': '0.50000',
                        'rank': 2,
                    },
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_recommendation_routes_require_authentication(self):
        self.client.force_authenticate(user=None)
        routes = (
            reverse('recommendation-list'),
            reverse('recommendation-detail', args=(self.recommendation.pk,)),
            reverse('project-recommendation-list', args=(self.project.pk,)),
        )

        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_recommendation_routes_resolve(self):
        self.assertEqual(
            resolve('/api/v1/recommendations/').url_name,
            'recommendation-list',
        )
        self.assertEqual(
            resolve(f'/api/v1/recommendations/{self.recommendation.pk}/').url_name,
            'recommendation-detail',
        )
        self.assertEqual(
            resolve(f'/api/v1/recommendations/projects/{self.project.pk}/').url_name,
            'project-recommendation-list',
        )
