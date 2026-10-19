from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()


class AccountsApiTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('register')
        self.login_url = reverse('login')
        self.refresh_url = reverse('token_refresh')
        self.logout_url = reverse('logout')
        self.me_url = reverse('me')
        self.password = 'Secure-random-password-928!'
        self.registration_data = {
            'username': 'new-user',
            'email': 'new-user@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'password': self.password,
            'password_confirmation': self.password,
        }

    def register_user(self):
        return User.objects.create_user(
            username='test-user',
            email='test-user@example.com',
            password=self.password,
        )

    def test_registration_hashes_password_and_returns_safe_profile(self):
        response = self.client.post(self.register_url, self.registration_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='new-user')
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_confirmation', response.data)
        self.assertEqual(response.data['email'], 'new-user@example.com')
        self.assertEqual(User.objects.count(), 1)

    def test_registration_rejects_duplicate_username(self):
        User.objects.create_user(
            username='new-user',
            email='existing@example.com',
            password=self.password,
        )

        response = self.client.post(self.register_url, self.registration_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 1)

    def test_registration_rejects_mismatched_password_confirmation(self):
        data = {**self.registration_data, 'password_confirmation': 'different'}

        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirmation', response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_rejects_weak_password(self):
        data = {
            **self.registration_data,
            'password': 'password',
            'password_confirmation': 'password',
        }

        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_requires_valid_email(self):
        data = {**self.registration_data, 'email': 'not-an-email'}

        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_login_returns_access_and_refresh_tokens(self):
        self.register_user()

        response = self.client.post(
            self.login_url,
            {'username': 'test-user', 'password': self.password},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_rejects_invalid_credentials(self):
        self.register_user()

        response = self.client.post(
            self.login_url,
            {'username': 'test-user', 'password': 'incorrect'},
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_rejects_inactive_user(self):
        user = self.register_user()
        user.is_active = False
        user.save(update_fields=('is_active',))

        response = self.client.post(
            self.login_url,
            {'username': 'test-user', 'password': self.password},
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_and_blacklists_the_previous_refresh_token(self):
        user = self.register_user()
        refresh = str(RefreshToken.for_user(user))

        response = self.client.post(self.refresh_url, {'refresh': refresh})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotEqual(response.data['refresh'], refresh)

        reused_response = self.client.post(self.refresh_url, {'refresh': refresh})
        self.assertEqual(reused_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_submitted_refresh_token(self):
        user = self.register_user()
        refresh = str(RefreshToken.for_user(user))

        response = self.client.post(self.logout_url, {'refresh': refresh})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reused_response = self.client.post(self.refresh_url, {'refresh': refresh})
        self.assertEqual(reused_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_requires_authentication_and_returns_safe_profile(self):
        unauthenticated_response = self.client.get(self.me_url)
        self.assertEqual(
            unauthenticated_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        user = self.register_user()
        access = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'test-user')
        self.assertNotIn('password', response.data)

    def test_profile_rejects_inactive_user(self):
        user = self.register_user()
        access = str(RefreshToken.for_user(user).access_token)
        user.is_active = False
        user.save(update_fields=('is_active',))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
