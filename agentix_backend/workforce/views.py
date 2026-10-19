from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from companies.models import CompanyUser
from .models import Department, Employee, EmployeeAIProfile, EmployeeSkill, Skill
from .permissions import IsCompanyWorkforceWriter
from .serializers import (
    DepartmentSerializer,
    EmployeeAIProfileSerializer,
    EmployeeSerializer,
    EmployeeSkillSerializer,
    SkillSerializer,
)


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


def writable_companies(user):
    return CompanyUser.objects.filter(
        user=user,
        role__in=(
            CompanyUser.Role.OWNER,
            CompanyUser.Role.ADMIN,
            CompanyUser.Role.MANAGER,
        ),
    ).values('company_id')


def ensure_employee_write_access(request, employee):
    if not CompanyUser.objects.filter(
        company=employee.department.company,
        user=request.user,
        role__in=(
            CompanyUser.Role.OWNER,
            CompanyUser.Role.ADMIN,
            CompanyUser.Role.MANAGER,
        ),
    ).exists():
        raise PermissionDenied(IsCompanyWorkforceWriter.message)


class DepartmentListCreateView(generics.ListCreateAPIView):
    serializer_class = DepartmentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Department.objects.filter(company_id__in=readable_companies(self.request.user))


class DepartmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DepartmentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Department.objects.filter(company_id__in=readable_companies(self.request.user))


class EmployeeListCreateView(generics.ListCreateAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Employee.objects.filter(
            department__company_id__in=readable_companies(self.request.user),
        )


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Employee.objects.filter(
            department__company_id__in=readable_companies(self.request.user),
        )


class EmployeeProfileView(generics.GenericAPIView):
    serializer_class = EmployeeAIProfileSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)
    http_method_names = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')

    def get_employee(self):
        return get_object_or_404(
            Employee.objects.filter(
                department__company_id__in=readable_companies(self.request.user),
            ),
            pk=self.kwargs['employee_id'],
        )

    def get_profile(self, employee):
        try:
            return employee.ai_profile
        except EmployeeAIProfile.DoesNotExist as exc:
            raise NotFound('AI profile not found.') from exc

    def get(self, request, *args, **kwargs):
        employee = self.get_employee()
        profile = self.get_profile(employee)
        return Response(self.get_serializer(profile).data)

    def post(self, request, *args, **kwargs):
        employee = self.get_employee()
        ensure_employee_write_access(request, employee)
        if EmployeeAIProfile.objects.filter(employee=employee).exists():
            return Response(
                {'detail': 'This employee already has an AI profile.'},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(employee=employee)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request, *args, **kwargs):
        return self.update_profile(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self.update_profile(request, partial=True)

    def update_profile(self, request, *, partial):
        employee = self.get_employee()
        ensure_employee_write_access(request, employee)
        profile = self.get_profile(employee)
        serializer = self.get_serializer(profile, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        employee = self.get_employee()
        ensure_employee_write_access(request, employee)
        profile = self.get_profile(employee)
        profile.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SkillListCreateView(generics.ListCreateAPIView):
    serializer_class = SkillSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Skill.objects.filter(company_id__in=readable_companies(self.request.user))


class SkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SkillSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return Skill.objects.filter(company_id__in=readable_companies(self.request.user))


class EmployeeSkillListCreateView(generics.ListCreateAPIView):
    serializer_class = EmployeeSkillSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return EmployeeSkill.objects.filter(
            employee__department__company_id__in=readable_companies(self.request.user),
            employee__department__company_id=F('skill__company_id'),
        ).select_related('employee', 'skill')


class EmployeeSkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeeSkillSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyWorkforceWriter)

    def get_queryset(self):
        return EmployeeSkill.objects.filter(
            employee__department__company_id__in=readable_companies(self.request.user),
            employee__department__company_id=F('skill__company_id'),
        ).select_related('employee', 'skill')
