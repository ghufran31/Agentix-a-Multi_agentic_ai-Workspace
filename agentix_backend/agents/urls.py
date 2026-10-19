from django.urls import path

from .views import AIAgentDetailView, AIAgentListCreateView


urlpatterns = [
    path('', AIAgentListCreateView.as_view(), name='ai-agent-list'),
    path('<int:pk>/', AIAgentDetailView.as_view(), name='ai-agent-detail'),
]
