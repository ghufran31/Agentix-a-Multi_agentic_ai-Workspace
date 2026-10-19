from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from companies.models import CompanyUser
from .models import Project, ProjectMember, ProjectRequirement
from .permissions import IsCompanyProjectWriter
from .serializers import (
    ProjectMemberSerializer,
    ProjectRequirementSerializer,
    ProjectSerializer,
)


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyProjectWriter)

    def get_queryset(self):
        return Project.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyProjectWriter)

    def get_queryset(self):
        return Project.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')


class NestedProjectView:
    permission_classes = (permissions.IsAuthenticated, IsCompanyProjectWriter)

    def get_project(self):
        if hasattr(self, '_parent_project'):
            return self._parent_project
        self._parent_project = get_object_or_404(
            Project.objects.filter(
                company_id__in=readable_companies(self.request.user),
            ),
            pk=self.kwargs['project_id'],
        )
        return self._parent_project

    def check_project_write_permission(self, project):
        self.check_object_permissions(self.request, project)


class NestedProjectListCreateView(NestedProjectView, generics.ListCreateAPIView):
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['project'] = self.get_project()
        return context

    def perform_create(self, serializer):
        project = self.get_project()
        self.check_project_write_permission(project)
        serializer.save(project=project)


class ProjectRequirementListCreateView(NestedProjectListCreateView):
    serializer_class = ProjectRequirementSerializer

    def get_queryset(self):
        return ProjectRequirement.objects.filter(
            project_id=self.kwargs['project_id'],
            project__company_id__in=readable_companies(self.request.user),
        ).select_related('project')


class ProjectRequirementDetailView(
    NestedProjectView,
    generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = ProjectRequirementSerializer

    def get_queryset(self):
        return ProjectRequirement.objects.filter(
            project_id=self.kwargs['project_id'],
            project__company_id__in=readable_companies(self.request.user),
        ).select_related('project')


class ProjectMemberListCreateView(NestedProjectListCreateView):
    serializer_class = ProjectMemberSerializer

    def get_queryset(self):
        return ProjectMember.objects.filter(
            project_id=self.kwargs['project_id'],
            project__company_id__in=readable_companies(self.request.user),
        ).select_related(
            'project',
            'employee__department',
            'ai_agent',
        )


class ProjectMemberDetailView(
    NestedProjectView,
    generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = ProjectMemberSerializer

    def get_queryset(self):
        return ProjectMember.objects.filter(
            project_id=self.kwargs['project_id'],
            project__company_id__in=readable_companies(self.request.user),
        ).select_related(
            'project',
            'employee__department',
            'ai_agent',
        )
