from django.urls import path

from .views import (
    DepartmentDetailView,
    DepartmentListCreateView,
    EmployeeDetailView,
    EmployeeListCreateView,
    EmployeeProfileView,
    EmployeeSkillDetailView,
    EmployeeSkillListCreateView,
    SkillDetailView,
    SkillListCreateView,
)


urlpatterns = [
    path('departments/', DepartmentListCreateView.as_view(), name='department-list'),
    path('departments/<int:pk>/', DepartmentDetailView.as_view(), name='department-detail'),
    path('employees/', EmployeeListCreateView.as_view(), name='employee-list'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path(
        'employees/<int:employee_id>/profile/',
        EmployeeProfileView.as_view(),
        name='employee-profile',
    ),
    path('skills/', SkillListCreateView.as_view(), name='skill-list'),
    path('skills/<int:pk>/', SkillDetailView.as_view(), name='skill-detail'),
    path('employee-skills/', EmployeeSkillListCreateView.as_view(), name='employee-skill-list'),
    path(
        'employee-skills/<int:pk>/',
        EmployeeSkillDetailView.as_view(),
        name='employee-skill-detail',
    ),
]
