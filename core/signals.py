from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Employee
from .ldap_utils import ldap_manager
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Employee)
def sync_employee_to_ad(sender, instance, created, **kwargs):
    """Automatically sync employee changes back to Active Directory."""
    # Skip if this is a newly created user (might not exist in AD yet if created locally)
    # or if it's a superuser not linked to AD
    if created or not instance.sAMAccountName or instance.is_superuser:
        return

    # Check if we should sync (e.g., if relevant fields changed)
    # Note: In a real production app, we might use a flag or check __init__ values
    # but for this specific request, we'll sync the core fields.
    
    ad_attrs = {
        'givenName': instance.first_name_en,
        'sn': instance.last_name_en,
        'displayName': instance.get_full_name_en(),
        'title': instance.job_title,
        'department': instance.department,
    }
    
    logger.info(f"Signal triggered: Syncing {instance.sAMAccountName} to Active Directory")
    
    success, message = ldap_manager.update_user_attributes(instance.sAMAccountName, ad_attrs)
    if not success:
        logger.error(f"Failed to sync {instance.sAMAccountName} to AD: {message}")
