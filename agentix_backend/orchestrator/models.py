from django.db import models

from companies.models import Company
from projects.models import Project


class ProjectCreationReceipt(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMMITTED = 'committed', 'Committed'

    id = models.BigAutoField(primary_key=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='project_creation_receipts',
    )
    project = models.OneToOneField(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='creation_receipt',
    )
    thread_id = models.CharField(max_length=255)
    execution_id = models.CharField(max_length=255)
    task_id = models.CharField(max_length=80)
    operation_key = models.CharField(max_length=64)
    canonical_payload = models.JSONField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_creation_receipts'
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'operation_key'),
                name='unique_company_project_creation_operation',
            )
        ]

# Create your models here.
