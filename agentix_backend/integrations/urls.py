from django.urls import path

from .views import ConnectionDetailView, ConnectionListCreateView


urlpatterns = [
    path('', ConnectionListCreateView.as_view(), name='connection-list'),
    path('<int:pk>/', ConnectionDetailView.as_view(), name='connection-detail'),
]
