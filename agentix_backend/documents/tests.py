from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from companies.models import Company, CompanyUser
from .models import CompanyDocument


User = get_user_model()


class CompanyDocumentApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='document-owner',
            email='document-owner@example.com',
            password='Safe-document-password-123!',
        )
        self.company = self.create_company(self.owner, 'Document company')
        self.document = CompanyDocument.objects.create(
            company=self.company,
            title='Policy',
            file_path='private/policies/policy.pdf',
        )
        self.client.force_authenticate(self.owner)
        self.list_url = reverse('document-list')

    def create_company(self, user, name):
        company = Company.objects.create(created_by_user=user, name=name)
        CompanyUser.objects.create(
            company=company,
            user=user,
            role=CompanyUser.Role.OWNER,
        )
        return company

    def create_other_company_and_document(self):
        user = User.objects.create_user(
            username='other-document-owner',
            email='other-document-owner@example.com',
            password='Safe-document-password-123!',
        )
        company = self.create_company(user, 'Other company')
        document = CompanyDocument.objects.create(
            company=company,
            title='Private document',
            file_path='private/other.pdf',
        )
        return company, document

    def test_create_document_metadata(self):
        response = self.client.post(
            self.list_url,
            {
                'company': self.company.pk,
                'title': 'Employee handbook',
                'document_type': 'policy',
                'description': 'Current handbook',
                'file_path': 'private/handbook.pdf',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['company'], self.company.pk)
        self.assertEqual(response.data['title'], 'Employee handbook')
        self.assertEqual(response.data['file_path'], 'private/handbook.pdf')
        self.assertTrue(
            CompanyDocument.objects.filter(
                pk=response.data['id'],
                file_path='private/handbook.pdf',
            ).exists()
        )

    def test_create_requires_title_and_allows_optional_fields(self):
        missing_title = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'description': 'No title'},
        )
        minimal = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'title': 'Minimal document'},
        )

        self.assertEqual(missing_title.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', missing_title.data)
        self.assertEqual(minimal.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(minimal.data['document_type'])
        self.assertIsNone(minimal.data['description'])
        self.assertIsNone(minimal.data['file_path'])
        self.assertTrue(minimal.data['uploaded_at'])

    def test_list_only_includes_member_companies(self):
        self.create_other_company_and_document()

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [self.document.pk])

    def test_retrieve_update_and_delete_document(self):
        detail_url = reverse('document-detail', args=(self.document.pk,))
        retrieve = self.client.get(detail_url)
        update = self.client.patch(
            detail_url,
            {'title': 'Updated policy', 'description': 'Revised'},
        )
        delete = self.client.delete(detail_url)

        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(update.data['title'], 'Updated policy')
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CompanyDocument.objects.filter(pk=self.document.pk).exists())

    def test_accessible_document_can_be_moved_only_to_an_authorized_company(self):
        second_company = Company.objects.create(
            created_by_user=User.objects.create_user(
                username='second-document-owner',
                email='second-document-owner@example.com',
                password='Safe-document-password-123!',
            ),
            name='Second company',
        )
        CompanyUser.objects.create(
            company=second_company,
            user=self.owner,
            role=CompanyUser.Role.ADMIN,
        )

        response = self.client.patch(
            reverse('document-detail', args=(self.document.pk,)),
            {'company': second_company.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company'], second_company.pk)

    def test_member_can_read_but_cannot_create_update_or_delete(self):
        member = User.objects.create_user(
            username='document-member',
            email='document-member@example.com',
            password='Safe-document-password-123!',
        )
        CompanyUser.objects.create(
            company=self.company,
            user=member,
            role=CompanyUser.Role.MEMBER,
        )
        self.client.force_authenticate(member)
        detail_url = reverse('document-detail', args=(self.document.pk,))

        read = self.client.get(detail_url)
        create = self.client.post(
            self.list_url,
            {'company': self.company.pk, 'title': 'Forbidden'},
        )
        update = self.client.patch(detail_url, {'title': 'Forbidden'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_company_ids_are_rejected_on_create_and_update(self):
        other_company, _ = self.create_other_company_and_document()
        create = self.client.post(
            self.list_url,
            {'company': other_company.pk, 'title': 'Unauthorized'},
        )
        update = self.client.patch(
            reverse('document-detail', args=(self.document.pk,)),
            {'company': other_company.pk},
        )
        nonexistent = self.client.post(
            self.list_url,
            {'company': 999999, 'title': 'Unknown'},
        )

        self.assertEqual(create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(update.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(nonexistent.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_company_documents_return_404_for_read_update_and_delete(self):
        _, other_document = self.create_other_company_and_document()
        detail_url = reverse('document-detail', args=(other_document.pk,))

        read = self.client.get(detail_url)
        update = self.client.patch(detail_url, {'title': 'Intrusion'})
        delete = self.client.delete(detail_url)

        self.assertEqual(read.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CompanyDocument.objects.filter(pk=other_document.pk).exists())

    def test_every_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        detail_url = reverse('document-detail', args=(self.document.pk,))

        responses = (
            self.client.get(self.list_url),
            self.client.post(self.list_url, {'company': self.company.pk, 'title': 'No auth'}),
            self.client.get(detail_url),
            self.client.patch(detail_url, {'title': 'No auth'}),
            self.client.delete(detail_url),
        )

        self.assertTrue(
            all(response.status_code == status.HTTP_401_UNAUTHORIZED for response in responses)
        )

    def test_document_routes_resolve(self):
        self.assertEqual(resolve('/api/v1/documents/').url_name, 'document-list')
        self.assertEqual(
            resolve('/api/v1/documents/1/').url_name,
            'document-detail',
        )
