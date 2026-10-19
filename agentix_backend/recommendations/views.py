from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from companies.models import CompanyUser
from projects.models import Project
from projects.permissions import IsCompanyProjectWriter
from .models import Recommendation
from .serializers import RecommendationSerializer


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


class RecommendationListCreateView(generics.ListCreateAPIView):
    serializer_class = RecommendationSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyProjectWriter)

    def get_queryset(self):
        return Recommendation.objects.filter(
            project__company_id__in=readable_companies(self.request.user),
        ).select_related(
            'project',
            'employee__department',
            'ai_agent',
        )


class RecommendationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RecommendationSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyProjectWriter)

    def get_queryset(self):
        return Recommendation.objects.filter(
            project__company_id__in=readable_companies(self.request.user),
        ).select_related(
            'project',
            'employee__department',
            'ai_agent',
        )


class ProjectRecommendationListView(generics.ListAPIView):
    serializer_class = RecommendationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_project(self):
        if not hasattr(self, '_project'):
            self._project = get_object_or_404(
                Project.objects.filter(
                    company_id__in=readable_companies(self.request.user),
                ),
                pk=self.kwargs['project_id'],
            )
        return self._project

    def get_queryset(self):
        project = self.get_project()
        return Recommendation.objects.filter(
            project=project,
        ).select_related(
            'project',
            'employee__department',
            'ai_agent',
        )
