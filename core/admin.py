from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import Employee, OUTransferAuditLog
from .ldap_utils import ldap_manager, AVAILABLE_OUS


@admin.register(OUTransferAuditLog)
class OUTransferAuditLogAdmin(admin.ModelAdmin):
    """Admin interface for OU Transfer Audit Log."""
    
    list_display = ('employee', 'old_ou_display', 'new_ou_display', 'changed_by', 'changed_at', 'status_badge')
    list_filter = ('status', 'changed_at', 'employee__department')
    search_fields = ('employee__sAMAccountName', 'employee__first_name_en', 'employee__last_name_en')
    readonly_fields = ('employee', 'old_ou', 'new_ou', 'changed_by', 'changed_at', 'error_message')
    date_hierarchy = 'changed_at'
    
    def old_ou_display(self, obj):
        """Display old OU in a more readable format."""
        return obj.old_ou or "N/A"
    old_ou_display.short_description = "Old OU"
    
    def new_ou_display(self, obj):
        """Display new OU in a more readable format."""
        return obj.new_ou or "N/A"
    new_ou_display.short_description = "New OU"
    
    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            'success': '#28a745',
            'failed': '#dc3545',
            'pending': '#ffc107',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"
    
    def has_add_permission(self, request):
        """Prevent manual creation of audit logs."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs."""
        return False


@admin.register(Employee)
class EmployeeAdmin(BaseUserAdmin):
    """Admin interface for Employee model."""
    
    fieldsets = (
        (None, {'fields': ('username', 'password', 'sAMAccountName')}),
        ('Personal Information (English)', {
            'fields': ('first_name_en', 'last_name_en'),
            'classes': ('wide',)
        }),
        ('Personal Information (Arabic)', {
            'fields': ('first_name_ar', 'last_name_ar'),
            'classes': ('wide', 'collapse'),
        }),
        ('Employee Information', {
            'fields': ('employee_id', 'national_id', 'job_title', 'department', 'hire_date'),
            'classes': ('wide',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'sAMAccountName', 'password1', 'password2'),
        }),
        ('Personal Information (English)', {
            'classes': ('wide',),
            'fields': ('first_name_en', 'last_name_en'),
        }),
        ('Personal Information (Arabic)', {
            'classes': ('wide', 'collapse'),
            'fields': ('first_name_ar', 'last_name_ar'),
        }),
        ('Employee Information', {
            'classes': ('wide',),
            'fields': ('employee_id', 'national_id', 'job_title', 'department', 'hire_date'),
        }),
    )
    
    list_display = ('username', 'sAMAccountName', 'first_name_en', 'last_name_en', 'employee_id', 'department', 'current_ou_display')
    list_filter = ('department', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'sAMAccountName', 'first_name_en', 'last_name_en', 'email', 'employee_id')
    ordering = ('last_name_en', 'first_name_en')
    actions = ['transfer_ou_action', 'sync_ou_from_ad']
    
    readonly_fields = ('date_joined', 'last_login')
    
    def get_readonly_fields(self, request, obj=None):
        """Make sAMAccountName readonly when editing (but editable when creating)."""
        readonly = list(self.readonly_fields)
        if obj is not None:  # Editing existing object
            readonly.append('sAMAccountName')
        return readonly
    
    def current_ou_display(self, obj):
        """Display the current OU from AD."""
        ou = ldap_manager.get_user_ou(obj.sAMAccountName)
        if ou:
            return format_html(
                '<span style="background-color: #e7f3ff; padding: 5px 10px; border-radius: 3px;">{}</span>',
                ou
            )
        return format_html('<span style="color: red;">Not found in AD</span>')
    current_ou_display.short_description = "Current OU (from AD)"
    
    def transfer_ou_action(self, request, queryset):
        """Admin action to transfer employee to different OU."""
        from django.shortcuts import render
        
        if 'apply' in request.POST:
            new_ou = request.POST.get('new_ou')
            if new_ou:
                transferred = 0
                failed = 0
                
                for employee in queryset:
                    # Get current OU
                    old_ou = ldap_manager.get_user_ou(employee.sAMAccountName)
                    
                    # Transfer in AD
                    success, message = ldap_manager.transfer_user_ou(
                        employee.sAMAccountName,
                        new_ou
                    )
                    
                    # Log the transfer
                    OUTransferAuditLog.objects.create(
                        employee=employee,
                        old_ou=old_ou,
                        new_ou=new_ou,
                        changed_by=request.user,
                        status='success' if success else 'failed',
                        error_message=message if not success else ''
                    )
                    
                    if success:
                        transferred += 1
                    else:
                        failed += 1
                
                message = f"Transferred {transferred} employee(s)"
                if failed > 0:
                    message += f", {failed} failed"
                self.message_user(request, message)
        else:
            # Show the form to select OU
            return render(request, 'admin/transfer_ou.html', {
                'employees': queryset,
                'ous': AVAILABLE_OUS,
                'opts': self.model._meta,
            })
    transfer_ou_action.short_description = "Transfer selected employees to different OU"
    
    def sync_ou_from_ad(self, request, queryset):
        """Admin action to sync OU information from AD."""
        synced = 0
        for employee in queryset:
            ou = ldap_manager.get_user_ou(employee.sAMAccountName)
            if ou:
                synced += 1
        
        self.message_user(request, f"Synced OU information for {synced} employee(s)")
    sync_ou_from_ad.short_description = "Sync OU information from Active Directory"


