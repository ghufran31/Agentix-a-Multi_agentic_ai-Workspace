from django.contrib import admin

from .models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = (
        'provider',
        'connection_type',
        'account_name',
        'status',
        'company',
        'connected_at',
    )
    search_fields = ('provider', 'connection_type', 'account_name', 'company__name')
    list_filter = ('status', 'provider', 'company', 'connected_at')
    ordering = ('company__name', 'provider')
    list_select_related = ('company',)
    date_hierarchy = 'connected_at'
    autocomplete_fields = ('company',)
