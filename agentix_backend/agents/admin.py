from django.contrib import admin

from .models import AIAgent


@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'agent_type', 'status', 'company', 'created_at')
    search_fields = ('name', 'agent_type', 'description', 'capabilities', 'company__name')
    list_filter = ('status', 'agent_type', 'company', 'created_at')
    ordering = ('company__name', 'name')
    list_select_related = ('company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('company',)
