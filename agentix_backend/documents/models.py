from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from companies.models import Company


class CompanyDocument(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    file_path = models.TextField(null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'company_documents'

    def __str__(self):
        return self.title
