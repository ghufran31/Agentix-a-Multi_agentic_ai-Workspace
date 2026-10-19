from rest_framework.permissions import BasePermission

from companies.models import CompanyUser


class IsCompanyProjectWriter(BasePermission):
    message = 'An owner, admin, or manager membership is required to modify projects.'

    writer_roles = (
        CompanyUser.Role.OWNER,
        CompanyUser.Role.ADMIN,
        CompanyUser.Role.MANAGER,
    )

    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return CompanyUser.objects.filter(
            user=request.user,
            role__in=self.writer_roles,
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        project = obj if hasattr(obj, 'company_id') else obj.project
        return CompanyUser.objects.filter(
            company_id=project.company_id,
            user=request.user,
            role__in=self.writer_roles,
        ).exists()
