from django.urls import path

from . import console_views as views

app_name = 'supervisor_console'
urlpatterns = [
    path('', views.console, name='console'),
    path('api/v1/conversations/', views.conversations, name='conversations'),
    path('api/v1/conversations/<str:thread>/messages/', views.messages, name='messages'),
    path('api/v1/conversations/<str:thread>/execution/', views.execution, name='execution'),
    path('api/v1/conversations/<str:thread>/events/', views.events, name='events'),
    path('api/v1/conversations/<str:thread>/approval/', views.approval, name='approval'),
]
