"""
Active Directory / LDAP Authentication Backend for Django
Uses ldap3 library to authenticate against Windows Server Active Directory
"""

import logging
from typing import Optional, Dict, Any
from ldap3 import Server, Connection, ALL, SIMPLE
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.conf import settings

logger = logging.getLogger(__name__)
Employee = get_user_model()


class LDAPBackend(ModelBackend):
    """
    Authenticate using Active Directory via LDAP.
    Credentials are validated against the domain controller.
    User must already exist in the local database.
    """

    def authenticate(self, request, username: str = None, password: str = None, **kwargs):
        """
        Authenticate user against Active Directory.
        
        Args:
            request: Django request object
            username: sAMAccountName (Windows login)
            password: User's password
            
        Returns:
            Employee object if authentication successful, None otherwise
        """
        if not username or not password:
            logger.warning("Authenticate called without username or password")
            return None

        try:
            # Attempt LDAP authentication
            ad_user_data = self._authenticate_ad(username, password)
            
            if ad_user_data is None:
                logger.warning(f"LDAP authentication failed for user: {username}")
                return None

            # Get employee from database by sAMAccountName
            # User must already exist in DB (created by admin or on first login)
            try:
                employee = Employee.objects.get(sAMAccountName=ad_user_data['sAMAccountName'])
                logger.info(f"Successfully authenticated user: {username}")
                return employee
            except Employee.DoesNotExist:
                logger.warning(f"User {username} authenticated in AD but not found in database")
                return None

        except Exception as e:
            logger.error(f"Error during LDAP authentication: {str(e)}", exc_info=True)
            return None

    def _authenticate_ad(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate against Active Directory via LDAP.
        
        Args:
            username: sAMAccountName (e.g., 'khaled')
            password: User's password
            
        Returns:
            Dictionary with user attributes if successful, None otherwise
        """
        try:
            # Get AD configuration from settings
            ad_server = getattr(settings, 'AD_SERVER', None)
            ad_port = getattr(settings, 'AD_PORT', 389)
            ad_use_ssl = getattr(settings, 'AD_USE_SSL', False)
            ad_base_dn = getattr(settings, 'AD_BASE_DN', 'DC=eissa,DC=local')
            ad_domain = getattr(settings, 'AD_DOMAIN', 'eissa.local')

            if not ad_server:
                logger.error("AD_SERVER not configured in settings")
                return None

            # Build the userPrincipalName for bind
            bind_dn_upn = f"{username}@{ad_domain}"

            # Connect to AD server
            server = Server(
                ad_server,
                port=ad_port,
                use_ssl=ad_use_ssl,
                get_info=ALL
            )

            # Try to bind with user credentials
            try:
                logger.debug(f"Attempting LDAP bind with UPN: {bind_dn_upn}")
                connection = Connection(
                    server,
                    user=bind_dn_upn,
                    password=password,
                    authentication=SIMPLE,
                    raise_exceptions=True
                )
                connection.bind()
                logger.debug(f"Successfully bound with UPN: {bind_dn_upn}")
            except Exception as e:
                logger.debug(f"Authentication failed: {str(e)}")
                return None

            # Search for user to get their attributes
            search_filter = f"(sAMAccountName={username})"
            search_base = f"OU=New,{ad_base_dn}"
            
            logger.debug(f"Searching for user with filter: {search_filter}")
            connection.search(
                search_base=search_base,
                search_filter=search_filter,
                attributes=['*']
            )

            if not connection.entries:
                logger.warning(f"User {username} not found in AD search")
                connection.unbind()
                return None

            # Extract user attributes from first result
            user_entry = connection.entries[0]
            ad_user_data = self._extract_user_attributes(user_entry)
            
            connection.unbind()
            logger.debug(f"Successfully retrieved AD attributes for user: {username}")
            return ad_user_data

        except Exception as e:
            logger.error(f"LDAP authentication error for {username}: {str(e)}", exc_info=True)
            return None

    def _extract_user_attributes(self, user_entry) -> Dict[str, Any]:
        """
        Extract relevant attributes from LDAP user entry.
        
        Args:
            user_entry: LDAP3 user entry object
            
        Returns:
            Dictionary with extracted attributes
        """
        try:
            attributes = {}

            # Basic attributes
            attributes['sAMAccountName'] = str(user_entry.sAMAccountName) if user_entry.sAMAccountName else None
            attributes['displayName'] = str(user_entry.displayName) if user_entry.displayName else None
            attributes['distinguishedName'] = str(user_entry.distinguishedName)

            # Contact information (not stored in DB, used for display)
            attributes['mail'] = str(user_entry.mail) if user_entry.mail else None
            attributes['telephoneNumber'] = str(user_entry.telephoneNumber) if user_entry.telephoneNumber else None
            
            # Department and OU information (not stored in DB)
            attributes['department'] = str(user_entry.department) if user_entry.department else None
            attributes['title'] = str(user_entry.title) if user_entry.title else None
            
            # Extract Organizational Unit from distinguished name
            dn = attributes['distinguishedName']
            ou_parts = [part for part in dn.split(',') if part.strip().startswith('OU=')]
            attributes['organizational_unit'] = ','.join(ou_parts) if ou_parts else None

            logger.debug(f"Extracted attributes: {list(attributes.keys())}")
            return attributes

        except Exception as e:
            logger.error(f"Error extracting user attributes: {str(e)}", exc_info=True)
            return {}

    def get_user(self, user_id: int) -> Optional[Employee]:
        """
        Get user by ID (used by Django for session management).
        
        Args:
            user_id: User's primary key
            
        Returns:
            Employee object or None
        """
        try:
            return Employee.objects.get(pk=user_id)
        except Employee.DoesNotExist:
            return None

