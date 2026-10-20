"""Permission-aware dashboard metrics built from existing PostgreSQL tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from agents.models import AIAgent
from companies.models import Company, CompanyUser
from documents.models import CompanyDocument
from integrations.models import Connection
from projects.models import Project
from recommendations.models import Recommendation
from workforce.models import Department, Employee

RECENT_LIMIT = 5
RECENT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class StatusBreakdown:
    label: str
    count: int


@dataclass(frozen=True)
class RecentItem:
    label: str
    url: str | None
    meta: str = ''


@dataclass
class MetricCard:
    key: str
    label: str
    count: int
    changelist_url: str | None = None
    add_url: str | None = None
    recent_window_count: int | None = None
    status_breakdown: list[StatusBreakdown] = field(default_factory=list)
    role_breakdown: list[StatusBreakdown] = field(default_factory=list)


@dataclass
class DashboardData:
    cards: list[MetricCard] = field(default_factory=list)
    recent_companies: list[RecentItem] = field(default_factory=list)
    recent_projects: list[RecentItem] = field(default_factory=list)
    recent_agents: list[RecentItem] = field(default_factory=list)
    recent_recommendations: list[RecentItem] = field(default_factory=list)
    quick_actions: list[RecentItem] = field(default_factory=list)
    is_empty: bool = True


def _has_view_permission(user, model) -> bool:
    opts = model._meta
    return (
        user.has_perm(f'{opts.app_label}.view_{opts.model_name}')
        or user.has_perm(f'{opts.app_label}.change_{opts.model_name}')
    )


def _has_add_permission(user, model) -> bool:
    opts = model._meta
    return user.has_perm(f'{opts.app_label}.add_{opts.model_name}')


def _admin_url(admin_site, model, action: str) -> str | None:
    opts = model._meta
    try:
        return reverse(
            f'admin:{opts.app_label}_{opts.model_name}_{action}',
            current_app=admin_site.name,
        )
    except NoReverseMatch:
        return None


def _status_breakdown(queryset, field_name: str) -> list[StatusBreakdown]:
    rows = (
        queryset.values(field_name)
        .annotate(total=Count('id'))
        .order_by('-total', field_name)
    )
    breakdown = []
    for row in rows:
        raw = row[field_name]
        label = raw if raw not in (None, '') else 'unset'
        breakdown.append(StatusBreakdown(label=str(label), count=row['total']))
    return breakdown


def _role_breakdown() -> list[StatusBreakdown]:
    rows = (
        CompanyUser.objects.values('role')
        .annotate(total=Count('id'))
        .order_by('-total', 'role')
    )
    labels = dict(CompanyUser.Role.choices)
    return [
        StatusBreakdown(label=labels.get(row['role'], row['role']), count=row['total'])
        for row in rows
    ]


def _recent_window_count(queryset, field_name: str = 'created_at') -> int:
    cutoff = timezone.now() - timedelta(days=RECENT_WINDOW_DAYS)
    return queryset.filter(**{f'{field_name}__gte': cutoff}).count()


def _object_change_url(admin_site, obj) -> str | None:
    opts = obj._meta
    try:
        return reverse(
            f'admin:{opts.app_label}_{opts.model_name}_change',
            args=[obj.pk],
            current_app=admin_site.name,
        )
    except NoReverseMatch:
        return None


def _recent_items(admin_site, queryset, label_fn, meta_fn, limit=RECENT_LIMIT):
    items = []
    for obj in queryset[:limit]:
        items.append(
            RecentItem(
                label=label_fn(obj),
                url=_object_change_url(admin_site, obj),
                meta=meta_fn(obj),
            )
        )
    return items


def build_dashboard(request, admin_site) -> DashboardData:
    """Assemble dashboard cards and recent lists the user is allowed to view."""
    user = request.user
    User = get_user_model()
    cards: list[MetricCard] = []
    quick_actions: list[RecentItem] = []

    metric_specs = [
        {
            'key': 'users',
            'label': 'Registered users',
            'model': User,
            'queryset': User.objects.all(),
            'recent_field': 'date_joined',
        },
        {
            'key': 'companies',
            'label': 'Companies',
            'model': Company,
            'queryset': Company.objects.all(),
            'recent_field': 'created_at',
        },
        {
            'key': 'memberships',
            'label': 'Company memberships',
            'model': CompanyUser,
            'queryset': CompanyUser.objects.all(),
            'recent_field': 'created_at',
            'roles': True,
        },
        {
            'key': 'departments',
            'label': 'Departments',
            'model': Department,
            'queryset': Department.objects.all(),
            'recent_field': 'created_at',
        },
        {
            'key': 'employees',
            'label': 'Employees',
            'model': Employee,
            'queryset': Employee.objects.all(),
            'recent_field': 'created_at',
        },
        {
            'key': 'agents',
            'label': 'AI agents',
            'model': AIAgent,
            'queryset': AIAgent.objects.all(),
            'recent_field': 'created_at',
            'status_field': 'status',
        },
        {
            'key': 'projects',
            'label': 'Projects',
            'model': Project,
            'queryset': Project.objects.all(),
            'recent_field': 'created_at',
            'status_field': 'status',
        },
        {
            'key': 'recommendations',
            'label': 'Recommendations',
            'model': Recommendation,
            'queryset': Recommendation.objects.all(),
            'recent_field': 'created_at',
            'status_field': 'status',
        },
        {
            'key': 'documents',
            'label': 'Documents',
            'model': CompanyDocument,
            'queryset': CompanyDocument.objects.all(),
            'recent_field': 'uploaded_at',
        },
        {
            'key': 'connections',
            'label': 'Integrations',
            'model': Connection,
            'queryset': Connection.objects.all(),
            'recent_field': None,
            'status_field': 'status',
        },
    ]

    for spec in metric_specs:
        model = spec['model']
        if not _has_view_permission(user, model):
            continue

        queryset = spec['queryset']
        changelist_url = _admin_url(admin_site, model, 'changelist')
        add_url = (
            _admin_url(admin_site, model, 'add')
            if _has_add_permission(user, model)
            else None
        )
        recent_field = spec.get('recent_field')
        recent_window_count = (
            _recent_window_count(queryset, recent_field)
            if recent_field
            else None
        )
        status_breakdown = (
            _status_breakdown(queryset, spec['status_field'])
            if spec.get('status_field')
            else []
        )
        role_breakdown = _role_breakdown() if spec.get('roles') else []

        cards.append(
            MetricCard(
                key=spec['key'],
                label=spec['label'],
                count=queryset.count(),
                changelist_url=changelist_url,
                add_url=add_url,
                recent_window_count=recent_window_count,
                status_breakdown=status_breakdown,
                role_breakdown=role_breakdown,
            )
        )

        if add_url:
            verbose = model._meta.verbose_name
            quick_actions.append(
                RecentItem(label=f'Add {verbose}', url=add_url)
            )

    recent_companies = []
    if _has_view_permission(user, Company):
        recent_companies = _recent_items(
            admin_site,
            Company.objects.select_related('created_by_user').order_by('-created_at'),
            label_fn=lambda obj: obj.name,
            meta_fn=lambda obj: obj.created_at.strftime('%Y-%m-%d'),
        )

    recent_projects = []
    if _has_view_permission(user, Project):
        recent_projects = _recent_items(
            admin_site,
            Project.objects.select_related('company').order_by('-created_at'),
            label_fn=lambda obj: obj.name,
            meta_fn=lambda obj: f'{obj.company.name} · {obj.status}',
        )

    recent_agents = []
    if _has_view_permission(user, AIAgent):
        recent_agents = _recent_items(
            admin_site,
            AIAgent.objects.select_related('company').order_by('-created_at'),
            label_fn=lambda obj: obj.name,
            meta_fn=lambda obj: f'{obj.company.name} · {obj.status}',
        )

    recent_recommendations = []
    if _has_view_permission(user, Recommendation):
        recent_recommendations = _recent_items(
            admin_site,
            Recommendation.objects.select_related(
                'project__company',
                'employee',
                'ai_agent',
            ).order_by('-created_at'),
            label_fn=lambda obj: (
                f'{obj.employee or obj.ai_agent} → {obj.project.name}'
            ),
            meta_fn=lambda obj: f'{obj.status} · rank {obj.rank}',
        )

    # Users almost always exist for a signed-in staff account; treat the
    # platform as empty when every other visible business metric is zero.
    business_cards = [card for card in cards if card.key != 'users']
    is_empty = bool(business_cards) and all(card.count == 0 for card in business_cards)

    return DashboardData(
        cards=cards,
        recent_companies=recent_companies,
        recent_projects=recent_projects,
        recent_agents=recent_agents,
        recent_recommendations=recent_recommendations,
        quick_actions=quick_actions[:8],
        is_empty=is_empty,
    )
