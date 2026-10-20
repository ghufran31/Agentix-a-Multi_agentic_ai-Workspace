from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

from .dashboard import build_dashboard

# Preferred app ordering on the Master Control index and sidebar.
APP_ORDER = {
    'auth': 10,
    'companies': 20,
    'workforce': 30,
    'agents': 40,
    'projects': 50,
    'recommendations': 60,
    'documents': 70,
    'integrations': 80,
    'token_blacklist': 90,
}


class AgentixAdminSite(AdminSite):
    """Branded AdminSite with a permission-aware Master Control dashboard."""

    site_header = _('Agentix Master Control Center')
    site_title = _('Agentix Admin')
    index_title = _('Master Control Center')
    site_url = None
    enable_nav_sidebar = True
    index_template = 'admin/index.html'
    login_template = 'admin/login.html'

    def each_context(self, request):
        context = super().each_context(request)
        context['agentix_admin_customization'] = True
        return context

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        app_list.sort(
            key=lambda app: (
                APP_ORDER.get(app['app_label'], 500),
                app['name'].lower(),
            )
        )
        return app_list

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['dashboard'] = build_dashboard(request, self)
        return super().index(request, extra_context=extra_context)
