from rest_framework import serializers

from companies.models import Company
from .models import Connection


class ConnectionSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = Connection
        fields = (
            'id',
            'company',
            'provider',
            'connection_type',
            'account_name',
            'status',
            'connected_at',
        )
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = Company.objects.filter(
                memberships__user=request.user,
                memberships__role__in=('owner', 'admin', 'manager'),
            ).distinct()
