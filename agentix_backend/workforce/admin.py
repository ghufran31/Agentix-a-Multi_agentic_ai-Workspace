from django import forms
from django.contrib import admin

from .models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill


class DepartmentAdminForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        current_company_id = None
        if self.instance.pk:
            current_company_id = Department.objects.filter(
                pk=self.instance.pk,
            ).values_list('company_id', flat=True).first()
        if (
            company
            and company.pk != current_company_id
            and EmployeeSkill.objects.filter(
                employee__department=self.instance,
            ).exclude(skill__company=company).exists()
        ):
            raise forms.ValidationError(
                'Moving this department would invalidate employee skills.'
            )
        return cleaned_data


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = '__all__'
        exclude = ('created_at',)

    def clean(self):
        cleaned_data = super().clean()
        department = cleaned_data.get('department')
        current_company_id = None
        if self.instance.pk:
            current_company_id = Employee.objects.filter(
                pk=self.instance.pk,
            ).values_list('department__company_id', flat=True).first()
        if (
            department
            and department.company_id != current_company_id
            and EmployeeSkill.objects.filter(
                employee_id=self.instance.pk,
            ).exclude(
                skill__company_id=department.company_id,
            ).exists()
        ):
            raise forms.ValidationError(
                'Moving this employee would invalidate employee skills.'
            )
        return cleaned_data


class EmployeeSkillAdminForm(forms.ModelForm):
    class Meta:
        model = EmployeeSkill
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        if 'employee' not in cleaned_data and self.instance.employee_id:
            employee = self.instance.employee
        skill = cleaned_data.get('skill')
        if 'skill' not in cleaned_data and self.instance.skill_id:
            skill = self.instance.skill
        if (
            employee
            and skill
            and employee.department.company_id != skill.company_id
        ):
            raise forms.ValidationError(
                'The employee and skill must belong to the same company.'
            )
        return cleaned_data


class SkillAdminForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        current_company_id = None
        if self.instance.pk:
            current_company_id = Skill.objects.filter(
                pk=self.instance.pk,
            ).values_list('company_id', flat=True).first()
        if (
            company
            and company.pk != current_company_id
            and self.instance.employee_assignments.exclude(
                employee__department__company=company,
            ).exists()
        ):
            raise forms.ValidationError(
                'Moving this skill would invalidate employee assignments.'
            )
        return cleaned_data


class EmployeeAIProfileInline(admin.StackedInline):
    model = EmployeeAIProfile
    extra = 0
    max_num = 1
    readonly_fields = ('updated_at',)


class EmployeeSkillInline(admin.TabularInline):
    model = EmployeeSkill
    form = EmployeeSkillAdminForm
    extra = 0
    autocomplete_fields = ('skill',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentAdminForm
    list_display = ('name', 'company', 'created_at')
    search_fields = ('name', 'company__name')
    list_filter = ('company', 'created_at')
    ordering = ('company__name', 'name')
    list_select_related = ('company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('company',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeAdminForm
    list_display = (
        'employee_code',
        'first_name',
        'last_name',
        'email',
        'department',
        'company_name',
        'created_at',
    )
    search_fields = (
        'employee_code',
        'first_name',
        'last_name',
        'email',
        'department__name',
        'department__company__name',
    )
    list_filter = ('department__company', 'department', 'created_at')
    ordering = ('last_name', 'first_name')
    list_select_related = ('department__company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('department',)
    inlines = (EmployeeAIProfileInline, EmployeeSkillInline)

    @admin.display(description='Company', ordering='department__company__name')
    def company_name(self, obj):
        return obj.department.company.name


@admin.register(EmployeeAIProfile)
class EmployeeAIProfileAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'job_title',
        'availability_status',
        'employment_status',
        'updated_at',
    )
    search_fields = (
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name',
        'employee__email',
        'job_title',
    )
    list_filter = (
        'availability_status',
        'employment_status',
        'employee__department__company',
    )
    ordering = ('employee__last_name', 'employee__first_name')
    list_select_related = ('employee__department__company',)
    readonly_fields = ('updated_at',)
    autocomplete_fields = ('employee',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    form = SkillAdminForm
    list_display = ('name', 'category', 'company', 'created_at')
    search_fields = ('name', 'category', 'company__name')
    list_filter = ('company', 'category', 'created_at')
    ordering = ('company__name', 'name')
    list_select_related = ('company',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('company',)


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    form = EmployeeSkillAdminForm
    list_display = ('employee', 'skill', 'company_name', 'proficiency', 'years_experience')
    search_fields = (
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name',
        'skill__name',
        'skill__category',
    )
    list_filter = ('skill__company', 'skill__category')
    ordering = ('employee__last_name', 'employee__first_name', 'skill__name')
    list_select_related = ('employee__department__company', 'skill__company')
    autocomplete_fields = ('employee', 'skill')

    @admin.display(description='Company', ordering='skill__company__name')
    def company_name(self, obj):
        return obj.skill.company.name
