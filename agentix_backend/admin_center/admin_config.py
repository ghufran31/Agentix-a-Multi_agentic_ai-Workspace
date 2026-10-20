from django.contrib.admin.apps import AdminConfig


class AgentixAdminConfig(AdminConfig):
    """Replace django.contrib.admin when Agentix admin customization is enabled."""

    default_site = 'admin_center.site.AgentixAdminSite'
