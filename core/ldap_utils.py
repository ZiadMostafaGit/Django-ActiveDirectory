"""
LDAP/Active Directory utilities for managing OU transfers and user operations.
"""

import logging
from typing import Optional, Dict, List, Tuple
from ldap3 import Server, Connection, ALL, SIMPLE, NTLM
from ldap3.core.exceptions import LDAPCursorAttributeError
from django.conf import settings

logger = logging.getLogger(__name__)


# Production OUs available in eissa.local Active Directory
# All OUs are under OU=New container: OU=New,DC=eissa,DC=local
AVAILABLE_OUS = {
    'Accountant': ('OU=Accountant,OU=New', 'المحاسبة'),
    'AdministrativeAffairs': ('OU=Administrative Affairs,OU=New', 'الشؤون الإدارية'),
    'Camera': ('OU=Camera,OU=New', 'الكاميرات'),
    'Exhibit': ('OU=Exhibit,OU=New', 'المعارض'),
    'HR': ('OU=HR,OU=New', 'الموارد البشرية'),
    'IT': ('OU=IT,OU=New', 'تكنولوجيا المعلومات'),
    'Audit': ('OU=Audit,OU=New', 'المراجعة'),
    'OutWork': ('OU=Out Work,OU=New', 'العمل الخارجي'),
    'Projects': ('OU=Projects,OU=New', 'المشاريع'),
    'Sales': ('OU=Sales,OU=New', 'المبيعات'),
    'Supplies': ('OU=Supplies,OU=New', 'المشتريات'),
    'Secretarial': ('OU=Secretarial,OU=New', 'السكرتارية'),
}


class LDAPManager:
    """Manager for LDAP operations with Active Directory."""
    
    def __init__(self):
        """Initialize LDAP manager with AD configuration."""
        self.ad_server = getattr(settings, 'AD_SERVER', None)
        self.ad_port = getattr(settings, 'AD_PORT', 389)
        self.ad_use_ssl = getattr(settings, 'AD_USE_SSL', False)
        self.ad_base_dn = getattr(settings, 'AD_BASE_DN', 'DC=eissa,DC=local')
        self.ad_domain = getattr(settings, 'AD_DOMAIN', 'eissa.local')
        
        if not self.ad_server:
            logger.error("AD_SERVER not configured in settings")
    
    def _get_connection(self) -> Optional[Connection]:
        """Create and return a connection to AD server.
        
        Returns:
            Connection object or None if connection fails
        """
        try:
            server = Server(
                self.ad_server,
                port=self.ad_port,
                use_ssl=self.ad_use_ssl,
                get_info=ALL
            )
            
            # Get admin credentials from settings
            ad_admin_user = getattr(settings, 'AD_ADMIN_USER', None)
            ad_admin_password = getattr(settings, 'AD_ADMIN_PASSWORD', None)

            if not ad_admin_user or not ad_admin_password:
                # Fallback to anonymous bind if no admin credentials (might fail on some ADs)
                logger.warning("No AD_ADMIN_USER/PASSWORD configured. Attempting anonymous bind.")
                connection = Connection(
                    server,
                    authentication=SIMPLE,
                    raise_exceptions=True
                )
            else:
                # Bind with admin credentials
                connection = Connection(
                    server,
                    user=ad_admin_user,
                    password=ad_admin_password,
                    authentication=SIMPLE,
                    raise_exceptions=True
                )
            
            connection.bind()
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to AD server: {str(e)}")
            return None
    
    def get_user_by_samaccount(self, sAMAccountName: str) -> Optional[Dict]:
        """Get user information from AD by sAMAccountName.
        
        Args:
            sAMAccountName: Windows login username
            
        Returns:
            Dictionary with user attributes or None if not found
        """
        try:
            connection = self._get_connection()
            if not connection:
                return None
            
            search_filter = f"(sAMAccountName={sAMAccountName})"
            
            # Auto-detect Base DN from rootDSE if possible
            actual_base_dn = self.ad_base_dn
            if connection.server and connection.server.info and connection.server.info.other:
                contexts = connection.server.info.other.get('defaultNamingContext')
                if contexts:
                    actual_base_dn = contexts[0]

            # List of containers to search in order of priority
            search_bases = [
                f"OU=New,{actual_base_dn}",
                f"CN=Users,{actual_base_dn}",
                f"CN=Administrators,{actual_base_dn}",
                actual_base_dn  # Fallback to root
            ]
            
            found_entry = None
            final_search_base = None

            for base in search_bases:
                try:
                    logger.debug(f"Searching for user {sAMAccountName} in {base}")
                    connection.search(
                        search_base=base,
                        search_filter=search_filter,
                        attributes=['*']
                    )
                    if connection.entries:
                        found_entry = connection.entries[0]
                        final_search_base = base
                        break
                except Exception as e:
                    logger.debug(f"Search failed in {base}: {str(e)}")
                    continue
            
            if not found_entry:
                logger.warning(f"User {sAMAccountName} not found in any AD container")
                connection.unbind()
                return None
            
            # Extract user attributes safely
            user_entry = found_entry
            
            def get_attr(entry, name, default=None):
                try:
                    attr = getattr(entry, name)
                    return str(attr) if attr else default
                except (LDAPCursorAttributeError, AttributeError):
                    return default

            user_data = {
                'sAMAccountName': get_attr(user_entry, 'sAMAccountName'),
                'displayName': get_attr(user_entry, 'displayName'),
                'distinguishedName': get_attr(user_entry, 'distinguishedName', ''),
                'mail': get_attr(user_entry, 'mail'),
                'telephoneNumber': get_attr(user_entry, 'telephoneNumber'),
                'department': get_attr(user_entry, 'department'),
                'title': get_attr(user_entry, 'title'),
            }
            
            # Extract OU from distinguished name
            dn = user_data['distinguishedName']
            ou_parts = [part for part in dn.split(',') if part.strip().startswith('OU=')]
            user_data['organizational_unit'] = ','.join(ou_parts) if ou_parts else None
            
            connection.unbind()
            logger.debug(f"Successfully retrieved AD data for user: {sAMAccountName}")
            return user_data
            
        except Exception as e:
            logger.error(f"Error retrieving user from AD: {str(e)}", exc_info=True)
            return None
    
    def transfer_user_ou(self, sAMAccountName: str, new_ou_name: str) -> Tuple[bool, str]:
        """Transfer user to a different Organizational Unit.
        
        Args:
            sAMAccountName: Windows login username
            new_ou_name: Name of the new OU (must be in AVAILABLE_OUS)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Validate OU exists
            if new_ou_name not in AVAILABLE_OUS:
                return False, f"OU '{new_ou_name}' not found in available list"
            
            # Get current user DN
            user_data = self.get_user_by_samaccount(sAMAccountName)
            if not user_data:
                return False, f"User '{sAMAccountName}' not found in AD"
            
            current_dn = user_data['distinguishedName']
            
            # Build new DN
            new_ou_partial = AVAILABLE_OUS[new_ou_name][0]  # e.g., "OU=IT,OU=New"
            new_dn = f"CN={sAMAccountName},{new_ou_partial},{self.ad_base_dn}"
            
            logger.info(f"Transferring user {sAMAccountName} from {current_dn} to {new_dn}")
            
            # Connect and perform modify DN operation
            connection = self._get_connection()
            if not connection:
                return False, "Failed to connect to AD server"
            
            # Extract CN from current DN
            cn_part = current_dn.split(',')[0]  # e.g., "CN=khaled"
            
            # Perform the modify DN operation
            try:
                connection.modify_dn(
                    current_dn,
                    cn_part,  # New RDN
                    new_superior=f"{new_ou_partial},{self.ad_base_dn}"
                )
                
                if connection.result['result'] == 0:
                    connection.unbind()
                    logger.info(f"Successfully transferred user {sAMAccountName} to OU {new_ou_name}")
                    return True, f"User transferred to {new_ou_name}"
                else:
                    error_msg = connection.result.get('message', 'Unknown error')
                    connection.unbind()
                    logger.error(f"Failed to transfer user: {error_msg}")
                    return False, error_msg
                    
            except Exception as e:
                connection.unbind()
                error_msg = str(e)
                logger.error(f"Error during modify_dn operation: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            logger.error(f"Error in transfer_user_ou: {str(e)}", exc_info=True)
            return False, str(e)

    def update_user_attributes(self, sAMAccountName: str, attributes: Dict[str, str]) -> Tuple[bool, str]:
        """Update user attributes in Active Directory.
        
        Args:
            sAMAccountName: Windows login username
            attributes: Dictionary of attributes to update (e.g., {'mail': 'new@mail.com'})
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Mapping from local field names to AD attribute names if needed
            # Currently we assume the keys in 'attributes' match AD attribute names
            
            user_data = self.get_user_by_samaccount(sAMAccountName)
            if not user_data:
                return False, f"User '{sAMAccountName}' not found in AD"
            
            dn = user_data['distinguishedName']
            
            connection = self._get_connection()
            if not connection:
                return False, "Failed to connect to AD server"
            
            # Prepare modifications
            from ldap3 import MODIFY_REPLACE
            changes = {}
            for attr, value in attributes.items():
                changes[attr] = [(MODIFY_REPLACE, [value])]
            
            logger.info(f"Updating AD attributes for {sAMAccountName} ({dn}): {attributes}")
            
            connection.modify(dn, changes)
            
            if connection.result['result'] == 0:
                connection.unbind()
                return True, "Successfully updated AD attributes"
            else:
                error_msg = connection.result.get('message', 'Unknown error')
                connection.unbind()
                logger.error(f"Failed to update AD attributes: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            logger.error(f"Error updating AD attributes: {str(e)}", exc_info=True)
            return False, str(e)

    def sync_users_from_container(self, container_path: str) -> List[Dict]:
        """Fetch all users from a specific AD container/OU.
        
        Args:
            container_path: Full DN or partial DN (e.g., 'CN=Users')
            
        Returns:
            List of user attribute dictionaries
        """
        try:
            connection = self._get_connection()
            if not connection:
                return []
            
            actual_base_dn = self.ad_base_dn
            if connection.server and connection.server.info and connection.server.info.other:
                contexts = connection.server.info.other.get('defaultNamingContext')
                if contexts:
                    actual_base_dn = contexts[0]
            
            # Build full search base if path is partial
            if ',' not in container_path:
                search_base = f"{container_path},{actual_base_dn}"
            else:
                search_base = container_path
            
            logger.info(f"Syncing users from container: {search_base}")
            
            connection.search(
                search_base=search_base,
                search_filter='(&(objectClass=user)(sAMAccountName=*))',
                attributes=['*']
            )
            
            users = []
            for entry in connection.entries:
                # Reuse attribute extraction logic if possible, or implement here
                def get_attr(entry, name, default=None):
                    try:
                        attr = getattr(entry, name)
                        return str(attr) if attr else default
                    except (LDAPCursorAttributeError, AttributeError):
                        return default

                data = {
                    'sAMAccountName': get_attr(entry, 'sAMAccountName'),
                    'displayName': get_attr(entry, 'displayName'),
                    'distinguishedName': get_attr(entry, 'distinguishedName', ''),
                    'mail': get_attr(entry, 'mail'),
                    'telephoneNumber': get_attr(entry, 'telephoneNumber'),
                    'department': get_attr(entry, 'department'),
                    'title': get_attr(entry, 'title'),
                }
                
                # Filter out system accounts (ending with $)
                if data['sAMAccountName'] and not data['sAMAccountName'].endswith('$'):
                    users.append(data)
            
            connection.unbind()
            return users
            
        except Exception as e:
            logger.error(f"Error syncing users from container: {str(e)}", exc_info=True)
            return []
    
    def get_user_ou(self, sAMAccountName: str) -> Optional[str]:
        """Get the current OU of a user.
        
        Args:
            sAMAccountName: Windows login username
            
        Returns:
            OU path or None if not found
        """
        user_data = self.get_user_by_samaccount(sAMAccountName)
        if user_data:
            return user_data.get('organizational_unit')
        return None
    
    @staticmethod
    def get_available_ous() -> Dict[str, Tuple[str, str]]:
        """Get list of available OUs.
        
        Returns:
            Dictionary with OU names and their display names
        """
        return AVAILABLE_OUS
    
    @staticmethod
    def get_ou_display_name(ou_name: str, lang: str = 'en') -> Optional[str]:
        """Get the display name of an OU.
        
        Args:
            ou_name: OU name in English
            lang: Language ('en' or 'ar')
            
        Returns:
            Display name in requested language or None
        """
        if ou_name not in AVAILABLE_OUS:
            return None
        
        idx = 1 if lang == 'ar' else 0
        return AVAILABLE_OUS[ou_name][idx] if idx == 0 else AVAILABLE_OUS[ou_name][1]


# Global LDAP manager instance
ldap_manager = LDAPManager()
