from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Company, CompanyUser


User = get_user_model()


class CompanySerializer(serializers.ModelSerializer):
    created_by_user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Company
        fields = (
            'id',
            'created_by_user',
            'name',
            'industry',
            'description',
            'email',
            'phone',
            'address',
            'created_at',
        )
        read_only_fields = ('id', 'created_by_user', 'created_at')


class CompanyDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ('name', 'industry', 'description', 'email', 'phone', 'address')


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')
        read_only_fields = fields


class CompanyMemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = CompanyUser
        fields = ('id', 'user', 'role', 'created_at')
        read_only_fields = fields
