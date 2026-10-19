from rest_framework.permissions import BasePermission

from .models import CompanyUser


class IsCompanyOwner(BasePermission):
    message = 'Only the company owner may update company details.'

    def has_object_permission(self, request, view, company):
        return CompanyUser.objects.filter(
            company=company,
            user=request.user,
            role=CompanyUser.Role.OWNER,
        ).exists()
