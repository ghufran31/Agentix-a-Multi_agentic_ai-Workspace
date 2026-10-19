from django.conf import settings
from django.db import models


class Company(models.Model):
    created_by_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_company',
    )
    name = models.CharField(max_length=255)
    industry = models.CharField(max_length=150, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'companies'

    def __str__(self):
        return self.name


class CompanyUser(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        MEMBER = 'member', 'Member'

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
    )
    role = models.CharField(
        max_length=7,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_users'
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'user'),
                name='unique_company_user_membership',
            )
        ]

    def __str__(self):
        return f'{self.user} - {self.company} ({self.role})'
