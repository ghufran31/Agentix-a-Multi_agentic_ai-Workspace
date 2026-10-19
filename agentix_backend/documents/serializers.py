from rest_framework import serializers

from companies.models import Company
from .models import CompanyDocument


class CompanyDocumentSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())

    class Meta:
        model = CompanyDocument
        fields = (
            'id',
            'company',
            'title',
            'document_type',
            'description',
            'file_path',
            'uploaded_at',
        )
        read_only_fields = ('id', 'uploaded_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.fields['company'].queryset = Company.objects.filter(
                memberships__user=request.user,
                memberships__role__in=('owner', 'admin', 'manager'),
            ).distinct()
