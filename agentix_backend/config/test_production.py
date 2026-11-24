from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import OperationalError
from django.test import SimpleTestCase


@skipUnless(settings.SETTINGS_MODULE == 'config.production', 'Requires production settings.')
class ProductionConfigurationTests(SimpleTestCase):
    def test_https_and_developer_console(self):
        self.assertFalse(settings.DEBUG)
        self.assertFalse(settings.AGENTIX_SUPERVISOR_CONSOLE_ENABLED)
        self.assertFalse(settings.AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES)
        self.assertEqual(self.client.get('/healthz/', headers={'Host': 'api.example.com'}).status_code, 301)
        self.assertEqual(self.client.get('/dev/supervisor/', secure=True,
                                         headers={'Host': 'api.example.com'}).status_code, 404)

    def test_jwt_endpoint_cors_is_origin_scoped(self):
        endpoint = '/api/v1/accounts/me/'
        # CORS headers are generated on preflight independent of JWT credentials.
        for origin, expected in (('https://app.example.com', 'https://app.example.com'),
                                 ('https://other.example.com', None)):
            with self.subTest(origin=origin):
                response = self.client.options(endpoint, secure=True, headers={
                    'Host': 'api.example.com', 'Origin': origin,
                    'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': 'authorization',
                })
                self.assertEqual(response.get('Access-Control-Allow-Origin'), expected)
                self.assertIsNone(response.get('Access-Control-Allow-Credentials'))

    @patch('config.production_urls.connection')
    def test_readiness_probes_database_and_hides_failures(self, db):
        headers = {'Host': 'api.example.com', 'X-Forwarded-Proto': 'https'}
        response = self.client.get('/healthz/', headers=headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        db.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SELECT 1')
        db.cursor.side_effect = OperationalError('private database details')
        response = self.client.get('/healthz/', headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})
