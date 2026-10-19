from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone

from agents.models import AIAgent
from projects.models import Project
from workforce.models import Employee


class Recommendation(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='recommendations',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='recommendations',
        null=True,
        blank=True,
    )
    ai_agent = models.ForeignKey(
        AIAgent,
        on_delete=models.CASCADE,
        related_name='recommendations',
        null=True,
        blank=True,
    )
    recommended_role = models.CharField(max_length=150, null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=5)
    rank = models.IntegerField()
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default='pending')
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'recommendations'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(employee__isnull=False, ai_agent__isnull=True)
                    | Q(employee__isnull=True, ai_agent__isnull=False)
                ),
                name='recommendation_exactly_one_candidate',
            )
        ]

    def __str__(self):
        candidate = self.employee or self.ai_agent
        return f'Recommendation for {candidate} on {self.project}'
