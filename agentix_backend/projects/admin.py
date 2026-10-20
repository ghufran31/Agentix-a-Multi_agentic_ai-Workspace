from django import forms
from django.contrib import admin

from .models import Project, ProjectMember, ProjectRequirement


class ProjectAdminForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        current_company_id = None
        if self.instance.pk:
            current_company_id = Project.objects.filter(
                pk=self.instance.pk,
            ).values_list('company_id', flat=True).first()
        if company and company.pk != current_company_id:
            incompatible_employee = self.instance.members.filter(
                employee__isnull=False,
            ).exclude(employee__department__company=company).exists()
            incompatible_agent = self.instance.members.filter(
                ai_agent__isnull=False,
            ).exclude(ai_agent__company=company).exists()
            if incompatible_employee or incompatible_agent:
                raise forms.ValidationError(
                    'Moving this project would invalidate existing members.'
                )
        return cleaned_data


class ProjectMemberAdminForm(forms.ModelForm):
    class Meta:
        model = ProjectMember
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        if 'employee' not in cleaned_data and self.instance.employee_id:
            employee = self.instance.employee
        ai_agent = cleaned_data.get('ai_agent')
        if 'ai_agent' not in cleaned_data and self.instance.ai_agent_id:
            ai_agent = self.instance.ai_agent
        if (employee is None) == (ai_agent is None):
            raise forms.ValidationError(
                'Exactly one of employee or AI agent must be selected.'
            )

        project = cleaned_data.get('project')
        if project is None and self.instance.project_id:
            project = self.instance.project
        if project and employee and employee.department.company_id != project.company_id:
            raise forms.ValidationError(
                'The employee must belong to the project company.'
            )
        if project and ai_agent and ai_agent.company_id != project.company_id:
            raise forms.ValidationError(
                'The AI agent must belong to the project company.'
            )
        return cleaned_data


class ProjectRequirementInline(admin.TabularInline):
    model = ProjectRequirement
    extra = 0
    readonly_fields = ('created_at',)


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    form = ProjectMemberAdminForm
    extra = 0
    autocomplete_fields = ('employee', 'ai_agent')
    readonly_fields = ('assigned_at',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    form = ProjectAdminForm
    list_display = (
        'name',
        'company',
        'status',
        'priority',
        'start_date',
        'deadline',
        'created_at',
    )
    search_fields = ('name', 'description', 'company__name')
    list_filter = ('status', 'priority', 'company', 'created_at')
    ordering = ('-created_at',)
    list_select_related = ('company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('company',)
    inlines = (ProjectRequirementInline, ProjectMemberInline)


@admin.register(ProjectRequirement)
class ProjectRequirementAdmin(admin.ModelAdmin):
    list_display = ('project', 'requirement_summary', 'priority', 'deadline', 'created_at')
    search_fields = (
        'project__name',
        'project__company__name',
        'requirement',
        'required_skills',
        'required_roles',
    )
    list_filter = ('priority', 'project__company', 'deadline', 'created_at')
    ordering = ('project__name', '-created_at')
    list_select_related = ('project__company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project',)

    @admin.display(description='Requirement')
    def requirement_summary(self, obj):
        return obj.requirement[:100]


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    form = ProjectMemberAdminForm
    list_display = (
        'project',
        'candidate',
        'member_type',
        'role',
        'status',
        'assigned_at',
    )
    search_fields = (
        'project__name',
        'project__company__name',
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name',
        'ai_agent__name',
        'role',
    )
    list_filter = ('member_type', 'status', 'project__company', 'assigned_at')
    ordering = ('-assigned_at',)
    list_select_related = (
        'project__company',
        'employee__department__company',
        'ai_agent__company',
    )
    date_hierarchy = 'assigned_at'
    readonly_fields = ('assigned_at',)
    autocomplete_fields = ('project', 'employee', 'ai_agent')

    @admin.display(description='Employee or AI agent')
    def candidate(self, obj):
        return obj.employee or obj.ai_agent
