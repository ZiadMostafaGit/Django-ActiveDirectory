from rest_framework import serializers
from .models import Employee, OUTransferAuditLog
from .ldap_utils import ldap_manager


class EmployeeADDataSerializer(serializers.Serializer):
    """
    Serializer for AD data - fetched dynamically from LDAP
    """
    email = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    current_ou = serializers.SerializerMethodField()
    
    def get_email(self, obj):
        """Get email from LDAP"""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            return user_data.get('mail') if user_data else None
        except Exception:
            return None
    
    def get_phone(self, obj):
        """Get phone from LDAP"""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            return user_data.get('telephoneNumber') if user_data else None
        except Exception:
            return None
    
    def get_display_name(self, obj):
        """Get display name from LDAP"""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            return user_data.get('displayName') if user_data else None
        except Exception:
            return None
    
    def get_current_ou(self, obj):
        """Get current OU from LDAP"""
        try:
            ou = ldap_manager.get_user_ou(obj.sAMAccountName)
            return ou
        except Exception:
            return None


class EmployeeSerializer(serializers.ModelSerializer):
    """
    Main Employee serializer with both DB and AD data
    """
    ad_data = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id',
            'employee_id',
            'sAMAccountName',
            'first_name_en',
            'last_name_en',
            'first_name_ar',
            'last_name_ar',
            'job_title',
            'department',
            'hire_date',
            'national_id',
            'username',
            'ad_data'
        ]
        read_only_fields = ['id', 'sAMAccountName']
    
    def get_ad_data(self, obj):
        """Fetch and include AD data"""
        ad_serializer = EmployeeADDataSerializer(obj)
        return ad_serializer.data


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for user profile endpoint
    """
    ad_data = serializers.SerializerMethodField()
    
    class Meta:
        model = Employee
        fields = [
            'id',
            'employee_id',
            'sAMAccountName',
            'username',
            'first_name_en',
            'last_name_en',
            'first_name_ar',
            'last_name_ar',
            'job_title',
            'department',
            'ad_data'
        ]
        read_only_fields = ['id', 'sAMAccountName']
    
    def get_ad_data(self, obj):
        """Fetch and include AD data"""
        ad_serializer = EmployeeADDataSerializer(obj)
        return ad_serializer.data


class OUTransferAuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for OU transfer audit logs
    """
    employee_sam = serializers.CharField(source='employee.sAMAccountName', read_only=True)
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = OUTransferAuditLog
        fields = [
            'id',
            'employee',
            'employee_sam',
            'old_ou',
            'new_ou',
            'changed_by',
            'changed_by_username',
            'changed_at',
            'status',
            'error_message'
        ]
        read_only_fields = fields
