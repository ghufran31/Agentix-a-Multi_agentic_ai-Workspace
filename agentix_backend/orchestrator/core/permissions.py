from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from companies.models import Company, CompanyUser


WRITER_ROLES = (
    CompanyUser.Role.OWNER,
    CompanyUser.Role.ADMIN,
    CompanyUser.Role.MANAGER,
)


@dataclass(frozen=True)
class DatabaseExecutionContext:
    user: object
    company: Company
    role: str
    read_only: bool = False

    def require_read(self):
        if not self.user or not self.user.is_authenticated:
            raise PermissionDenied('Authentication is required.')

    def require_write(self):
        self.require_read()
        if self.read_only:
            raise PermissionDenied('The database agent is in read-only mode.')
        if self.role not in WRITER_ROLES:
            raise PermissionDenied('The current role cannot modify company data.')


def database_context(user, company_id, read_only=False):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Authentication is required.')
    membership = (
        CompanyUser.objects.select_related('company')
        .filter(user=user, company_id=company_id)
        .first()
    )
    if not membership:
        raise PermissionDenied('The company is outside the authenticated user scope.')
    return DatabaseExecutionContext(
        user=user,
        company=membership.company,
        role=membership.role,
        read_only=read_only,
    )
