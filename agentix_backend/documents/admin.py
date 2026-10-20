from django.contrib import admin

from .models import CompanyDocument


@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'document_type', 'company', 'uploaded_at')
    search_fields = ('title', 'document_type', 'company__name', 'description')
    list_filter = ('company', 'document_type', 'uploaded_at')
    ordering = ('-uploaded_at',)
    list_select_related = ('company',)
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('uploaded_at',)
    autocomplete_fields = ('company',)
