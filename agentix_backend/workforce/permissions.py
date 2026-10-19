from rest_framework.permissions import BasePermission

from companies.models import CompanyUser


class IsCompanyWorkforceWriter(BasePermission):
    message = 'An owner, admin, or manager membership is required to modify workforce data.'

    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return CompanyUser.objects.filter(
            user=request.user,
            role__in=(
                CompanyUser.Role.OWNER,
                CompanyUser.Role.ADMIN,
                CompanyUser.Role.MANAGER,
            ),
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        company = getattr(obj, 'company', None)
        if company is None and hasattr(obj, 'department'):
            company = obj.department.company
        if company is None and hasattr(obj, 'employee'):
            employee = obj.employee
            company = employee.department.company
        if company is None:
            return False
        return CompanyUser.objects.filter(
            company=company,
            user=request.user,
            role__in=(
                CompanyUser.Role.OWNER,
                CompanyUser.Role.ADMIN,
                CompanyUser.Role.MANAGER,
            ),
        ).exists()
