from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'employees', views.EmployeeViewSet, basename='employee')
router.register(r'audit-logs', views.OUTransferAuditLogViewSet, basename='auditlog')

urlpatterns = [
    # API endpoints
    path('api/auth/login/', views.login_view, name='api_login'),
    path('api/employee/profile/', views.profile_view, name='api_profile'),
    path('api/', include(router.urls)),
]
