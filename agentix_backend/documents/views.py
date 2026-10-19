from rest_framework import generics, permissions

from companies.models import CompanyUser
from .models import CompanyDocument
from .permissions import IsCompanyDocumentWriter
from .serializers import CompanyDocumentSerializer


def readable_companies(user):
    return CompanyUser.objects.filter(user=user).values('company_id')


class CompanyDocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = CompanyDocumentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyDocumentWriter)

    def get_queryset(self):
        return CompanyDocument.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')


class CompanyDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyDocumentSerializer
    permission_classes = (permissions.IsAuthenticated, IsCompanyDocumentWriter)

    def get_queryset(self):
        return CompanyDocument.objects.filter(
            company_id__in=readable_companies(self.request.user),
        ).select_related('company')
