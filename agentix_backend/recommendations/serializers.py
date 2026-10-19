from rest_framework import serializers

from agents.models import AIAgent
from companies.models import CompanyUser
from projects.models import Project
from workforce.models import Employee
from .models import Recommendation


WRITER_ROLES = ('owner', 'admin', 'manager')


def writable_companies(user):
    return CompanyUser.objects.filter(
        user=user,
        role__in=WRITER_ROLES,
    ).values('company_id')


class RecommendationSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none())
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
        model = Recommendation
        fields = (
            'id',
            'project',
            'employee',
            'ai_agent',
            'recommended_role',
            'score',
            'rank',
            'reason',
            'status',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            companies = writable_companies(request.user)
            self.fields['project'].queryset = Project.objects.filter(
                company_id__in=companies,
            ).distinct()
            self.fields['employee'].queryset = Employee.objects.filter(
                department__company_id__in=companies,
            ).distinct()
            self.fields['ai_agent'].queryset = AIAgent.objects.filter(
                company_id__in=companies,
            ).distinct()

    def validate(self, attrs):
        if self.instance:
            if attrs.get('employee') is not None and 'ai_agent' not in attrs:
                attrs['ai_agent'] = None
            elif attrs.get('ai_agent') is not None and 'employee' not in attrs:
                attrs['employee'] = None

        project = attrs.get(
            'project',
            self.instance.project if self.instance else None,
        )
        employee = attrs.get(
            'employee',
            self.instance.employee if self.instance else None,
        )
        ai_agent = attrs.get(
            'ai_agent',
            self.instance.ai_agent if self.instance else None,
        )

        if (employee is None) == (ai_agent is None):
            raise serializers.ValidationError(
                'Exactly one of employee or ai_agent must be provided.'
            )

        if employee and employee.department.company_id != project.company_id:
            raise serializers.ValidationError(
                {'employee': 'The employee must belong to the project company.'}
            )
        if ai_agent and ai_agent.company_id != project.company_id:
            raise serializers.ValidationError(
                {'ai_agent': 'The AI agent must belong to the project company.'}
            )
        return attrs
