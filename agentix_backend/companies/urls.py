from django.urls import path

from .views import (
    CompanyDetailView,
    CompanyListCreateView,
    CompanyMembersView,
)


urlpatterns = [
    path('', CompanyListCreateView.as_view(), name='company-list-create'),
    path('<int:pk>/', CompanyDetailView.as_view(), name='company-detail'),
    path('<int:pk>/members/', CompanyMembersView.as_view(), name='company-members'),
]
