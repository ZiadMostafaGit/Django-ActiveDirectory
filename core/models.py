from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone


class EmployeeManager(BaseUserManager):
    """Custom manager for Employee model."""
    
    def create_user(self, username, sAMAccountName, password=None, **extra_fields):
        """Create and save a regular employee user."""
        if not username:
            raise ValueError('The Username must be set')
        if not sAMAccountName:
            raise ValueError('The sAMAccountName must be set')
        
        user = self.model(username=username, sAMAccountName=sAMAccountName, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, sAMAccountName, password=None, **extra_fields):
        """Create and save a superuser for admin access."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, sAMAccountName, password, **extra_fields)

    def get_by_natural_key(self, username):
        """Get user by natural key (username)."""
        return self.get(**{self.model.USERNAME_FIELD: username})


class Employee(AbstractUser):
    """Employee model storing only database-relevant information.
    
    AD information (email, phone, OU, displayName, etc.) is fetched on-demand
    and not stored in the database to ensure it's always in sync with AD.
    """
    
    # Link to Active Directory (immutable)
    sAMAccountName = models.CharField(
        max_length=100,
        unique=True,
        help_text="Active Directory sAMAccountName (Windows login). Used to link to AD."
    )
    
    # Override email field from AbstractUser - make it optional since it comes from AD
    email = models.EmailField(
        blank=True,
        null=True,
        default='',
        help_text="Leave empty. Email comes from Active Directory."
    )
    
    # Database-only fields (editable)
    employee_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique employee ID"
    )
    
    first_name_en = models.CharField(
        max_length=150,
        help_text="First name in English"
    )
    
    last_name_en = models.CharField(
        max_length=150,
        help_text="Last name in English"
    )
    
    first_name_ar = models.CharField(
        max_length=150,
        blank=True,
        help_text="First name in Arabic"
    )
    
    last_name_ar = models.CharField(
        max_length=150,
        blank=True,
        help_text="Last name in Arabic"
    )
    
    job_title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Job title"
    )
    
    department = models.CharField(
        max_length=100,
        blank=True,
        help_text="Department"
    )
    
    hire_date = models.DateField(
        null=True,
        blank=True,
        help_text="Hire date"
    )
    
    national_id = models.CharField(
        max_length=20,
        unique=True,
        help_text="National ID number"
    )
    
    # Custom manager
    objects = EmployeeManager()

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['last_name_en', 'first_name_en']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['sAMAccountName']),
            models.Index(fields=['national_id']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return f"{self.get_full_name_en()} ({self.username})"

    def get_full_name_en(self):
        """Return full name in English."""
        return f"{self.first_name_en} {self.last_name_en}".strip()

    def get_full_name_ar(self):
        """Return full name in Arabic."""
        if self.first_name_ar and self.last_name_ar:
            return f"{self.first_name_ar} {self.last_name_ar}".strip()
        return self.get_full_name_en()


class OUTransferAuditLog(models.Model):
    """Audit log for OU (Organizational Unit) transfers."""
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='ou_transfers',
        help_text="Employee whose OU was changed"
    )
    
    old_ou = models.CharField(
        max_length=500,
        blank=True,
        help_text="Previous Organizational Unit"
    )
    
    new_ou = models.CharField(
        max_length=500,
        help_text="New Organizational Unit"
    )
    
    changed_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ou_changes_made',
        help_text="Admin who made the change"
    )
    
    changed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of change"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Status of the transfer operation"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Error message if transfer failed"
    )
    
    class Meta:
        verbose_name = "OU Transfer Audit Log"
        verbose_name_plural = "OU Transfer Audit Logs"
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['employee', '-changed_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_en()} transferred to {self.new_ou} at {self.changed_at}"







