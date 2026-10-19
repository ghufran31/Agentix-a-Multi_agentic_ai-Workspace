from rest_framework import serializers

from companies.models import Company
from .models import (
    Department,
    Employee,
    EmployeeAIProfile,
    EmployeeSkill,
    Skill,
)


def writable_company_queryset(request):
    return Company.objects.filter(
        memberships__user=request.user,
        memberships__role__in=('owner', 'admin', 'manager'),
    ).distinct()


class DepartmentSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = Department
        fields = ('id', 'company', 'name', 'description', 'created_at')
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = writable_company_queryset(request)

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and company != self.instance.company:
            has_incompatible_assignments = EmployeeSkill.objects.filter(
                employee__department=self.instance,
            ).exclude(skill__company=company).exists()
            if has_incompatible_assignments:
                raise serializers.ValidationError(
                    {'company': 'Moving this department would invalidate employee skills.'}
                )
        return attrs


class EmployeeSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.none(),
    )
    email = serializers.EmailField(
        max_length=255,
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Employee
        fields = (
            'id',
            'department',
            'employee_code',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'date_of_birth',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['department'].queryset = Department.objects.filter(
                company__in=writable_company_queryset(request),
            ).distinct()

    def validate(self, attrs):
        department = attrs.get('department', getattr(self.instance, 'department', None))
        if (
            self.instance
            and department
            and department.company_id != self.instance.department.company_id
            and self.instance.skill_assignments.exclude(
                skill__company_id=department.company_id,
            ).exists()
        ):
            raise serializers.ValidationError(
                {'department': 'Moving this employee would invalidate employee skills.'}
            )
        return attrs


class EmployeeAIProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeAIProfile
        fields = (
            'id',
            'job_title',
            'education',
            'experience_years',
            'performance_score',
            'availability_status',
            'current_workload',
            'previous_project_score',
            'completed_projects',
            'employment_status',
            'updated_at',
        )
        read_only_fields = ('id', 'updated_at')


class SkillSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = Skill
        fields = ('id', 'company', 'name', 'category', 'description', 'created_at')
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = writable_company_queryset(request)

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if (
            self.instance
            and company != self.instance.company
            and self.instance.employee_assignments.exclude(
                employee__department__company=company,
            ).exists()
        ):
            raise serializers.ValidationError(
                {'company': 'Moving this skill would invalidate employee skills.'}
            )
        return attrs


class EmployeeSkillSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.none(),
    )
    skill = serializers.PrimaryKeyRelatedField(queryset=Skill.objects.none())

    class Meta:
        model = EmployeeSkill
        fields = (
            'id',
            'employee',
            'skill',
            'proficiency',
            'years_experience',
        )
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            companies = writable_company_queryset(request)
            self.fields['employee'].queryset = Employee.objects.filter(
                department__company__in=companies,
            ).distinct()
            self.fields['skill'].queryset = Skill.objects.filter(
                company__in=companies,
            ).distinct()

    def validate(self, attrs):
        employee = attrs.get('employee', getattr(self.instance, 'employee', None))
        skill = attrs.get('skill', getattr(self.instance, 'skill', None))
        if employee and skill and employee.department.company_id != skill.company_id:
            raise serializers.ValidationError(
                {'skill': 'The employee and skill must belong to the same company.'}
            )
        return attrs
