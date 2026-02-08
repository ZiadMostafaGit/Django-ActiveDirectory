from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import Employee, OUTransferAuditLog
from .serializers import EmployeeSerializer, EmployeeProfileSerializer, OUTransferAuditLogSerializer
from .ldap_utils import ldap_manager


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Login endpoint using AD credentials
    
    POST /api/auth/login/
    Body: {
        "sAMAccountName": "khaledAD",
        "password": "password123"
    }
    
    Returns:
    {
        "refresh": "...",
        "access": "...",
        "user": { Employee data with AD info }
    }
    """
    sAMAccountName = request.data.get('sAMAccountName')
    password = request.data.get('password')
    
    if not sAMAccountName or not password:
        return Response(
            {"error": "sAMAccountName and password required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Authenticate using LDAP backend
    user = authenticate(request, username=sAMAccountName, password=password)
    
    if user is None:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": EmployeeSerializer(user).data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """
    Get current user profile with AD data
    
    GET /api/employee/profile/
    
    Headers: Authorization: Bearer <access_token>
    
    Returns: Employee data with AD info
    """
    serializer = EmployeeProfileSerializer(request.user)
    return Response(serializer.data)


class EmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing employees
    
    GET /api/employees/ - List all employees
    GET /api/employees/{id}/ - Get employee detail
    """
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Only return non-superuser employees"""
        return Employee.objects.filter(is_superuser=False).order_by('employee_id')


class OUTransferAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing OU transfer audit logs
    
    GET /api/audit-logs/ - List all transfers
    GET /api/audit-logs/{id}/ - Get transfer detail
    """
    queryset = OUTransferAuditLog.objects.all().order_by('-changed_at')
    serializer_class = OUTransferAuditLogSerializer
    permission_classes = [IsAuthenticated]
