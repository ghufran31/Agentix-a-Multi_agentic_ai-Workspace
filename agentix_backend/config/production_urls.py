from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .urls import urlpatterns as api_urls


@never_cache
@require_safe
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


urlpatterns = [path('healthz/', readiness, name='readiness'), *api_urls]
