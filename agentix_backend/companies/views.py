from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Company, CompanyUser
from .permissions import IsCompanyOwner
from .serializers import (
    CompanyDetailsSerializer,
    CompanyMemberSerializer,
    CompanySerializer,
)


class CompanyListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = CompanySerializer

    def get_queryset(self):
        return Company.objects.filter(
            memberships__user=self.request.user,
        ).distinct()

    def create(self, request, *args, **kwargs):
        serializer = CompanyDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if Company.objects.filter(created_by_user=request.user).exists():
            return Response(
                {'detail': 'This user already created a company.'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                company = Company.objects.create(
                    created_by_user=request.user,
                    **serializer.validated_data,
                )
                CompanyUser.objects.create(
                    company=company,
                    user=request.user,
                    role=CompanyUser.Role.OWNER,
                )
        except IntegrityError:
            return Response(
                {'detail': 'The company could not be created due to a conflicting record.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_201_CREATED,
        )


class CompanyDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ('get', 'patch', 'head', 'options')

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return CompanyDetailsSerializer
        return CompanySerializer

    def get_object(self):
        company = super().get_object()
        if self.request.method == 'PATCH' and not IsCompanyOwner().has_object_permission(
            self.request,
            self,
            company,
        ):
            raise PermissionDenied(IsCompanyOwner.message)
        return company

    def get_queryset(self):
        return Company.objects.filter(memberships__user=self.request.user).distinct()


class CompanyMembersView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = CompanyMemberSerializer

    def get_queryset(self):
        company = get_object_or_404(
            Company.objects.filter(memberships__user=self.request.user).distinct(),
            pk=self.kwargs['pk'],
        )
        return CompanyUser.objects.filter(company=company).select_related('user')
