from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from companies.models import Company


class Department(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='departments',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'departments'

    def __str__(self):
        return f'{self.name} ({self.company})'


class Employee(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='employees',
    )
    employee_code = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'employees'
        constraints = [
            models.UniqueConstraint(
                fields=('department', 'employee_code'),
                name='unique_department_employee_code',
            )
        ]

    def __str__(self):
        return f'{self.employee_code}: {self.first_name} {self.last_name}'


class EmployeeAIProfile(models.Model):
    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        PARTIALLY_AVAILABLE = 'partially_available', 'Partially available'
        UNAVAILABLE = 'unavailable', 'Unavailable'

    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ON_LEAVE = 'on_leave', 'On leave'

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='ai_profile',
    )
    job_title = models.CharField(max_length=150, null=True, blank=True)
    education = models.CharField(max_length=255, null=True, blank=True)
    experience_years = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    performance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE,
    )
    current_workload = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    previous_project_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    completed_projects = models.IntegerField(default=0)
    employment_status = models.CharField(
        max_length=10,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    updated_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'employee_ai_profiles'

    def __str__(self):
        return f'AI profile for {self.employee}'


class Skill(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='skills',
    )
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = 'skills'
        constraints = [
            models.UniqueConstraint(
                fields=('company', 'name'),
                name='unique_company_skill_name',
            )
        ]

    def __str__(self):
        return self.name


class EmployeeSkill(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='skill_assignments',
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name='employee_assignments',
    )
    proficiency = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    years_experience = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = 'employee_skills'
        constraints = [
            models.UniqueConstraint(
                fields=('employee', 'skill'),
                name='unique_employee_skill',
            )
        ]

    def __str__(self):
        return f'{self.employee} - {self.skill}'
