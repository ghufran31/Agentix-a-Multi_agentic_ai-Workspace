from rest_framework import generics, permissions

from companies.models import CompanyUser
from .models import AIAgent
from .permissions import IsCompanyAgentWriter
from .serializers import AIAgentSerializer


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


class AIAgentListCreateView(generics.ListCreateAPIView):
    serializer_class = AIAgentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyAgentWriter)

    def get_queryset(self):
        return AIAgent.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')


class AIAgentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AIAgentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyAgentWriter)

    def get_queryset(self):
        return AIAgent.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')
