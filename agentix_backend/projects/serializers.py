from rest_framework import serializers

from agents.models import AIAgent
from companies.models import Company
from workforce.models import Employee
from .models import Project, ProjectMember, ProjectRequirement


def writable_company_queryset(request):
    return Company.objects.filter(
        memberships__user=request.user,
        memberships__role__in=('owner', 'admin', 'manager'),
    ).distinct()


class ProjectSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = Project
        fields = (
            'id',
            'company',
            'name',
            'description',
            'status',
            'priority',
            'start_date',
            'deadline',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = writable_company_queryset(request)

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        if self.instance and company != self.instance.company:
            incompatible_employee = self.instance.members.filter(
                employee__isnull=False,
            ).exclude(employee__department__company=company).exists()
            incompatible_agent = self.instance.members.filter(
                ai_agent__isnull=False,
            ).exclude(ai_agent__company=company).exists()
            if incompatible_employee or incompatible_agent:
                raise serializers.ValidationError(
                    {'company': 'Moving this project would invalidate existing members.'}
                )
        return attrs


class ProjectRequirementSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProjectRequirement
        fields = (
            'id',
            'project',
            'requirement',
            'required_skills',
            'required_roles',
            'priority',
            'deadline',
            'created_at',
        )
        read_only_fields = ('id', 'project', 'created_at')


class ProjectMemberSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.none(),
        allow_null=True,
        required=False,
    )
    ai_agent = serializers.PrimaryKeyRelatedField(
        queryset=AIAgent.objects.none(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = ProjectMember
        fields = (
            'id',
            'project',
            'employee',
            'ai_agent',
            'role',
            'member_type',
            'status',
            'assigned_at',
        )
        read_only_fields = ('id', 'project', 'assigned_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            companies = writable_company_queryset(request)
            self.fields['employee'].queryset = Employee.objects.filter(
                department__company__in=companies,
            ).distinct()
            self.fields['ai_agent'].queryset = AIAgent.objects.filter(
                company__in=companies,
            ).distinct()

    def validate(self, attrs):
        employee = attrs.get('employee', getattr(self.instance, 'employee', None))
        ai_agent = attrs.get('ai_agent', getattr(self.instance, 'ai_agent', None))
        if (employee is None) == (ai_agent is None):
            raise serializers.ValidationError(
                'Exactly one of employee or ai_agent must be provided.'
            )

        project = self.instance.project if self.instance else self.context.get('project')
        if employee and employee.department.company_id != project.company_id:
            raise serializers.ValidationError(
                {'employee': 'The employee must belong to the project company.'}
            )
        if ai_agent and ai_agent.company_id != project.company_id:
            raise serializers.ValidationError(
                {'ai_agent': 'The AI agent must belong to the project company.'}
            )
        return attrs
