from django.apps import AppConfig


class AdminCenterConfig(AppConfig):
    """Presentation assets and dashboard helpers; defines no models."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_center'
    verbose_name = 'Agentix Admin Center'
