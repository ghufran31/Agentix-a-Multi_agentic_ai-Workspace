"""Production profile for the Compose deployment behind Dokploy's TLS proxy."""
from urllib.parse import urlsplit

from .settings import *  # noqa: F403


def _values(name):
    return [value.strip() for value in os.environ.get(name, '').split(',') if value.strip()]


def _https_origins(name):
    origins = _values(name)
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            parsed.port
        except ValueError:
            raise ImproperlyConfigured(f'{name} must contain exact HTTPS origins.') from None
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.path or parsed.query or parsed.fragment or '*' in origin
                or any(char.isspace() for char in origin)):
            raise ImproperlyConfigured(f'{name} must contain exact HTTPS origins.')
    return origins


DEBUG = False
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('Set a strong DJANGO_SECRET_KEY of at least 50 characters.')

ALLOWED_HOSTS = _values('DJANGO_ALLOWED_HOSTS')
if not ALLOWED_HOSTS or any(
    host.startswith('.') or any(char in host for char in '*:/\\@')
    or any(char.isspace() for char in host) for host in ALLOWED_HOSTS
):
    raise ImproperlyConfigured('Set DJANGO_ALLOWED_HOSTS to exact API hostnames without schemes or ports.')

CSRF_TRUSTED_ORIGINS = _https_origins('DJANGO_CSRF_TRUSTED_ORIGINS')
CORS_ALLOWED_ORIGINS = _https_origins('DJANGO_CORS_ALLOWED_ORIGINS')
CORS_URLS_REGEX = r'^/api/v1/'
CORS_ALLOW_CREDENTIALS = False

INSTALLED_APPS = [*INSTALLED_APPS, 'corsheaders']
MIDDLEWARE = [
    MIDDLEWARE[0],
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *MIDDLEWARE[1:],
]
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'OPTIONS': {
            'host': os.environ.get('SMTP_HOST', 'localhost'),
            'port': int(os.environ.get('SMTP_PORT', '587')),
            'username': os.environ.get('SMTP_USER', ''),
            'password': os.environ.get('SMTP_PASSWORD', ''),
            'use_tls': True,
            'timeout': 10,
        },
    },
}
DEFAULT_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', 'Agentix <noreply@example.com>')

AGENTIX_SUPERVISOR_CONSOLE_ENABLED = False
AGENTIX_SUPERVISOR_CONSOLE_MODE = 'mock'
AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES = False
ROOT_URLCONF = 'config.production_urls'
