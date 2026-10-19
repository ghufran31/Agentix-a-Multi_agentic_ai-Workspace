from django.urls import path

from .views import (
    ProjectDetailView,
    ProjectListCreateView,
    ProjectMemberDetailView,
    ProjectMemberListCreateView,
    ProjectRequirementDetailView,
    ProjectRequirementListCreateView,
)


urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    path(
        '<int:project_id>/requirements/',
        ProjectRequirementListCreateView.as_view(),
        name='project-requirement-list',
    ),
    path(
        '<int:project_id>/requirements/<int:pk>/',
        ProjectRequirementDetailView.as_view(),
        name='project-requirement-detail',
    ),
    path(
        '<int:project_id>/members/',
        ProjectMemberListCreateView.as_view(),
        name='project-member-list',
    ),
    path(
        '<int:project_id>/members/<int:pk>/',
        ProjectMemberDetailView.as_view(),
        name='project-member-detail',
    ),
]
