from rest_framework import generics, permissions

from companies.models import CompanyUser
from .models import Connection
from .permissions import IsCompanyConnectionWriter
from .serializers import ConnectionSerializer


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


class ConnectionListCreateView(generics.ListCreateAPIView):
    serializer_class = ConnectionSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyConnectionWriter)

    def get_queryset(self):
        return Connection.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')


class ConnectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ConnectionSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyConnectionWriter)

    def get_queryset(self):
        return Connection.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')
