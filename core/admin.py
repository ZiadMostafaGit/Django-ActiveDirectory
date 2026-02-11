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
        ('Database Link to AD', {
            'fields': ('username', 'sAMAccountName'),
            'description': 'sAMAccountName links this employee to their Active Directory account. Password and email are in AD.'
        }),
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
        ('Active Directory Info', {
            'fields': ('current_ou_display', 'get_ad_email', 'get_ad_phone', 'get_ad_display_name'),
            'classes': ('wide',),
            'description': 'Real-time information fetched from Active Directory'
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
        ('Database Link to AD (Required)', {
            'classes': ('wide',),
            'fields': ('username', 'sAMAccountName'),
            'description': 'sAMAccountName must match the Active Directory login. Authentication uses AD credentials.'
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
    
    list_display = ('username', 'sAMAccountName', 'first_name_en', 'last_name_en', 'employee_id', 'department', 'current_ou_display', 'is_active')
    list_filter = ('department', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'sAMAccountName', 'first_name_en', 'last_name_en', 'employee_id')
    ordering = ('last_name_en', 'first_name_en')
    actions = ['transfer_ou_action', 'sync_details_from_ad_action', 'import_users_from_containers_action', 'full_sync_from_root_action']
    
    readonly_fields = ('date_joined', 'last_login', 'current_ou_display', 'get_ad_email', 'get_ad_phone', 'get_ad_display_name')
    
    def get_readonly_fields(self, request, obj=None):
        """Make sAMAccountName readonly when editing (but editable when creating)."""
        readonly = list(self.readonly_fields)
        if obj is not None:  # Editing existing object
            readonly.append('sAMAccountName')
            readonly.append('username')
        return readonly

    def save_model(self, request, obj, form, change):
        """Override save_model to update AD attributes when changed in Admin."""
        if change:  # Only for updates, not creation
            ad_attrs = {}
            if 'first_name_en' in form.changed_data or 'last_name_en' in form.changed_data:
                ad_attrs['givenName'] = obj.first_name_en
                ad_attrs['sn'] = obj.last_name_en
                ad_attrs['displayName'] = f"{obj.first_name_en} {obj.last_name_en}"
            
            if 'job_title' in form.changed_data:
                ad_attrs['title'] = obj.job_title
            
            if 'department' in form.changed_data:
                ad_attrs['department'] = obj.department

            if ad_attrs:
                success, message = ldap_manager.update_user_attributes(obj.sAMAccountName, ad_attrs)
                if success:
                    self.message_user(request, f"Successfully updated AD attributes for {obj.sAMAccountName}")
                else:
                    self.message_user(request, f"Failed to update AD: {message}", level='ERROR')
        
        super().save_model(request, obj, form, change)
    
    def current_ou_display(self, obj):
        """Display the current OU from AD."""
        try:
            ou = ldap_manager.get_user_ou(obj.sAMAccountName)
            if ou:
                return format_html(
                    '<span style="background-color: #e7f3ff; padding: 5px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
                    ou
                )
            return format_html('<span style="color: orange;">Not found in OU</span>')
        except Exception as e:
            return format_html('<span style="color: red;">Error: {}</span>', str(e)[:50])
    current_ou_display.short_description = "📍 Current OU (from AD)"
    
    def get_ad_email(self, obj):
        """Get email from AD."""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            if user_data:
                return user_data.get('mail') or '—'
            return '—'
        except Exception:
            return '—'
    get_ad_email.short_description = "📧 Email (from AD)"
    
    def get_ad_phone(self, obj):
        """Get phone from AD."""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            if user_data:
                return user_data.get('telephoneNumber') or '—'
            return '—'
        except Exception:
            return '—'
    get_ad_phone.short_description = "☎️ Phone (from AD)"
    
    def get_ad_display_name(self, obj):
        """Get display name from AD."""
        try:
            user_data = ldap_manager.get_user_by_samaccount(obj.sAMAccountName)
            if user_data:
                return user_data.get('displayName') or '—'
            return '—'
        except Exception:
            return '—'
    get_ad_display_name.short_description = "👤 Display Name (from AD)"
    
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
    
    def sync_details_from_ad_action(self, request, queryset):
        """Admin action to sync all information from AD for selected users."""
        synced = 0
        failed = 0
        for employee in queryset:
            user_data = ldap_manager.get_user_by_samaccount(employee.sAMAccountName)
            if user_data:
                employee.first_name_en = user_data.get('givenName') or user_data.get('displayName', '').split(' ')[0]
                employee.last_name_en = user_data.get('sn') or ' '.join(user_data.get('displayName', '').split(' ')[1:])
                employee.job_title = user_data.get('title') or ''
                employee.department = user_data.get('department') or ''
                employee.email = user_data.get('mail') or ''
                employee.save()
                synced += 1
            else:
                failed += 1
        
        self.message_user(request, f"Successfully synced {synced} employee(s) from AD. {failed} not found in AD.")
    sync_details_from_ad_action.short_description = "Sync all details from Active Directory"

    def import_users_from_containers_action(self, request, queryset=None):
        """Admin action (can be called without selection) to import new users from common containers."""
        containers = ['CN=Users', 'OU=New']
        total_created = 0
        
        for container in containers:
            ad_users = ldap_manager.sync_users_from_container(container)
            for ad_user in ad_users:
                sam = ad_user['sAMAccountName']
                if not sam: continue
                
                employee, created = Employee.objects.get_or_create(
                    sAMAccountName=sam,
                    defaults={
                        'username': sam,
                        'first_name_en': ad_user.get('displayName', '').split(' ')[0],
                        'last_name_en': ' '.join(ad_user.get('displayName', '').split(' ')[1:]),
                        'email': ad_user.get('mail') or '',
                        'job_title': ad_user.get('title') or '',
                        'department': ad_user.get('department') or '',
                        'employee_id': f"AD-{sam}",
                        'national_id': f"AD-{sam}",
                    }
                )
                if created:
                    total_created += 1
        
        if total_created > 0:
            self.message_user(request, f"Successfully imported {total_created} new users from AD containers.")
        else:
            self.message_user(request, "No new users found to import.")
    import_users_from_containers_action.short_description = "Import new users from AD (Users & New containers)"

    def full_sync_from_root_action(self, request, queryset=None):
        """Admin action to perform a deep search from the root base DN."""
        from django.conf import settings
        root_dn = getattr(settings, 'AD_BASE_DN', '')
        
        if not root_dn:
             self.message_user(request, "AD_BASE_DN not configured in settings", level='ERROR')
             return

        ad_users = ldap_manager.sync_users_from_container(root_dn)
        total_created = 0
        
        for ad_user in ad_users:
            sam = ad_user['sAMAccountName']
            if not sam: continue
            
            employee, created = Employee.objects.get_or_create(
                sAMAccountName=sam,
                defaults={
                    'username': sam,
                    'first_name_en': ad_user.get('displayName', '').split(' ')[0],
                    'last_name_en': ' '.join(ad_user.get('displayName', '').split(' ')[1:]),
                    'email': ad_user.get('mail') or '',
                    'job_title': ad_user.get('title') or '',
                    'department': ad_user.get('department') or '',
                    'employee_id': f"AD-{sam}",
                    'national_id': f"AD-{sam}",
                }
            )
            if created:
                total_created += 1
        
        self.message_user(request, f"Full root sync completed. Found {len(ad_users)} users, imported {total_created} new ones.")
    full_sync_from_root_action.short_description = "🚨 Force Full Sync from AD (Root)"


