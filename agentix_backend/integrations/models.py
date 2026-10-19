from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from companies.models import Company


class Connection(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='connections',
    )
    provider = models.CharField(max_length=100)
    connection_type = models.CharField(max_length=100, null=True, blank=True)
    account_name = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default='disconnected')
    connected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'connections'

    def __str__(self):
        return f'{self.provider} ({self.status})'
