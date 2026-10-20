from django import forms
from django.contrib import admin

from .models import Recommendation


class RecommendationAdminForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        ai_agent = cleaned_data.get('ai_agent')
        if (employee is None) == (ai_agent is None):
            raise forms.ValidationError(
                'Exactly one of employee or AI agent must be selected.'
            )

        project = cleaned_data.get('project')
        if project and employee and employee.department.company_id != project.company_id:
            raise forms.ValidationError(
                'The employee must belong to the project company.'
            )
        if project and ai_agent and ai_agent.company_id != project.company_id:
            raise forms.ValidationError(
                'The AI agent must belong to the project company.'
            )
        return cleaned_data


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    form = RecommendationAdminForm
    list_display = (
        'project',
        'candidate',
        'recommended_role',
        'score',
        'rank',
        'status',
        'created_at',
    )
    search_fields = (
        'project__name',
        'project__company__name',
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name',
        'ai_agent__name',
        'recommended_role',
        'reason',
    )
    list_filter = ('status', 'project__company', 'created_at')
    ordering = ('project__name', 'rank')
    list_select_related = (
        'project__company',
        'employee__department__company',
        'ai_agent__company',
    )
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project', 'employee', 'ai_agent')

    @admin.display(description='Employee or AI agent')
    def candidate(self, obj):
        return obj.employee or obj.ai_agent
