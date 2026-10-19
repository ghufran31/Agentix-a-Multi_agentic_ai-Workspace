from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from companies.models import Company


class AIAgent(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='ai_agents',
    )
    name = models.CharField(max_length=150)
    agent_type = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    capabilities = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default='active')
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'ai_agents'

    def __str__(self):
        return self.name
