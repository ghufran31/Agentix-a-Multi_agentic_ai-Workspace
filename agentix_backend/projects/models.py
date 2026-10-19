from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone

from agents.models import AIAgent
from companies.models import Company
from workforce.models import Employee


class Project(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='projects',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default='draft')
    priority = models.CharField(max_length=50, default='medium')
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'projects'

    def __str__(self):
        return self.name


class ProjectRequirement(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='requirements',
    )
    requirement = models.TextField()
    required_skills = models.TextField(null=True, blank=True)
    required_roles = models.TextField(null=True, blank=True)
    priority = models.CharField(max_length=50, default='medium')
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'project_requirements'

    def __str__(self):
        return f'Requirement for {self.project}: {self.requirement[:50]}'


class ProjectMember(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='members',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='project_memberships',
        null=True,
        blank=True,
    )
    ai_agent = models.ForeignKey(
        AIAgent,
        on_delete=models.CASCADE,
        related_name='project_memberships',
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=150, null=True, blank=True)
    member_type = models.CharField(max_length=50)
    status = models.CharField(max_length=50, default='active')
    assigned_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'project_members'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(employee__isnull=False, ai_agent__isnull=True)
                    | Q(employee__isnull=True, ai_agent__isnull=False)
                ),
                name='project_member_exactly_one_candidate',
            )
        ]

    def __str__(self):
        candidate = self.employee or self.ai_agent
        return f'{candidate} on {self.project}'
