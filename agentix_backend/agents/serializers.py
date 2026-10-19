from rest_framework import serializers

from companies.models import Company
from .models import AIAgent


class AIAgentSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = AIAgent
        fields = (
            'id',
            'company',
            'name',
            'agent_type',
            'description',
            'capabilities',
            'status',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = Company.objects.filter(
                memberships__user=request.user,
                memberships__role__in=('owner', 'admin', 'manager'),
            ).distinct()
