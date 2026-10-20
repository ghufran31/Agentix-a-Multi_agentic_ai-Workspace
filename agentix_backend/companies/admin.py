from django.contrib import admin

from .models import Company, CompanyUser


class CompanyUserInline(admin.TabularInline):
    model = CompanyUser
    extra = 0
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'created_by_user', 'email', 'created_at')
    search_fields = (
        'name',
        'industry',
        'email',
        'created_by_user__username',
        'created_by_user__email',
    )
    list_filter = ('created_at',)
    ordering = ('name',)
    list_select_related = ('created_by_user',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    inlines = (CompanyUserInline,)


@admin.register(CompanyUser)
class CompanyUserAdmin(admin.ModelAdmin):
    list_display = ('company', 'user', 'role', 'created_at')
    search_fields = (
        'company__name',
        'user__username',
        'user__email',
        'user__first_name',
        'user__last_name',
    )
    list_filter = ('role', 'created_at')
    ordering = ('company__name', 'user__username')
    list_select_related = ('company', 'user')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('company', 'user')
