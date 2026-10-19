from django.urls import path

from .views import CompanyDocumentDetailView, CompanyDocumentListCreateView


urlpatterns = [
    path('', CompanyDocumentListCreateView.as_view(), name='document-list'),
    path('<int:pk>/', CompanyDocumentDetailView.as_view(), name='document-detail'),
]
