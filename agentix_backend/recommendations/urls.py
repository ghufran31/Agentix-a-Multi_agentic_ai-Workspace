from django.urls import path

from .views import (
    ProjectRecommendationListView,
    RecommendationDetailView,
    RecommendationListCreateView,
)


urlpatterns = [
    path('', RecommendationListCreateView.as_view(), name='recommendation-list'),
    path(
        'projects/<int:project_id>/',
        ProjectRecommendationListView.as_view(),
        name='project-recommendation-list',
    ),
    path('<int:pk>/', RecommendationDetailView.as_view(), name='recommendation-detail'),
]
