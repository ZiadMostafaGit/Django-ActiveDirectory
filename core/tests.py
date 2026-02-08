"""
Comprehensive unit tests for Employee model, LDAP authentication, and AD operations.
"""

from django.test import TestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model, authenticate
from django.utils import timezone
from datetime import date
from unittest.mock import Mock, patch, MagicMock
from core.auth_backends import LDAPBackend
from core.models import OUTransferAuditLog
from core.ldap_utils import ldap_manager, AVAILABLE_OUS
import logging

Employee = get_user_model()


class EmployeeModelTests(TestCase):
    """Test cases for Employee model"""

    def setUp(self):
        """Set up test data"""
        self.employee_data = {
            'username': 'khaled',
            'sAMAccountName': 'khaled',
            'first_name_en': 'Mohamed',
            'last_name_en': 'Khaled',
            'first_name_ar': 'محمد',
            'last_name_ar': 'خالد',
            'employee_id': 'EMP001',
            'national_id': '123456789',
            'hire_date': date(2020, 1, 15),
            'job_title': 'Developer',
            'department': 'IT',
        }

    def test_create_employee_with_sam_account(self):
        """Test creating employee with sAMAccountName"""
        employee = Employee.objects.create_user(
            username=self.employee_data['username'],
            sAMAccountName=self.employee_data['sAMAccountName'],
            password='testpass123'
        )
        
        self.assertEqual(employee.username, self.employee_data['username'])
        self.assertEqual(employee.sAMAccountName, self.employee_data['sAMAccountName'])
        self.assertTrue(employee.is_active)

    def test_create_employee_with_all_fields(self):
        """Test creating employee with all fields"""
        employee = Employee.objects.create_user(
            **self.employee_data,
            password='testpass123'
        )
        
        self.assertEqual(employee.employee_id, self.employee_data['employee_id'])
        self.assertEqual(employee.national_id, self.employee_data['national_id'])
        self.assertEqual(employee.hire_date, self.employee_data['hire_date'])
        self.assertEqual(employee.job_title, self.employee_data['job_title'])
        self.assertEqual(employee.department, self.employee_data['department'])

    def test_sam_account_name_is_required(self):
        """Test that sAMAccountName is required"""
        with self.assertRaises(ValueError) as context:
            Employee.objects.create_user(
                username='testuser',
                sAMAccountName=None,
                password='testpass123'
            )
        self.assertIn('sAMAccountName', str(context.exception))

    def test_create_superuser(self):
        """Test creating a superuser"""
        superuser = Employee.objects.create_superuser(
            username='admin',
            sAMAccountName='admin',
            password='admin123'
        )
        
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_active)

    def test_employee_string_representation(self):
        """Test employee __str__ method"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name_en='Mohamed',
            last_name_en='Khaled'
        )
        
        expected_str = "Mohamed Khaled (khaled)"
        self.assertEqual(str(employee), expected_str)

    def test_get_full_name_english(self):
        """Test get_full_name_en method"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name_en='Mohamed',
            last_name_en='Khaled'
        )
        
        self.assertEqual(employee.get_full_name_en(), 'Mohamed Khaled')

    def test_get_full_name_arabic(self):
        """Test get_full_name_ar method"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name_en='Mohamed',
            last_name_en='Khaled',
            first_name_ar='محمد',
            last_name_ar='خالد'
        )
        
        self.assertEqual(employee.get_full_name_ar(), 'محمد خالد')

    def test_get_full_name_arabic_fallback(self):
        """Test get_full_name_ar falls back to English if Arabic not provided"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name_en='Mohamed',
            last_name_en='Khaled'
        )
        
        self.assertEqual(employee.get_full_name_ar(), 'Mohamed Khaled')

    def test_unique_constraints(self):
        """Test unique constraints on key fields"""
        Employee.objects.create_user(
            username='user1',
            sAMAccountName='khaled',
            employee_id='EMP001',
            national_id='123456789'
        )
        
        # Duplicate sAMAccountName should fail
        with self.assertRaises(Exception):
            Employee.objects.create_user(
                username='user2',
                sAMAccountName='khaled',
            )

    def test_employee_queryset_ordering(self):
        """Test employees are ordered by last_name_en, first_name_en"""
        Employee.objects.create_user(
            username='user1', sAMAccountName='user1',
            first_name_en='Zara', last_name_en='Smith',
            employee_id='EMP_Z1', national_id='111111111'
        )
        Employee.objects.create_user(
            username='user2', sAMAccountName='user2',
            first_name_en='Alice', last_name_en='Smith',
            employee_id='EMP_A1', national_id='222222222'
        )
        Employee.objects.create_user(
            username='user3', sAMAccountName='user3',
            first_name_en='Bob', last_name_en='Jones',
            employee_id='EMP_B1', national_id='333333333'
        )
        
        employees = list(Employee.objects.all())
        
        # Should be ordered: Jones Bob, Smith Alice, Smith Zara
        self.assertEqual(employees[0].last_name_en, 'Jones')
        self.assertEqual(employees[1].first_name_en, 'Alice')
        self.assertEqual(employees[2].first_name_en, 'Zara')


class OUTransferAuditLogTests(TestCase):
    """Test cases for OUTransferAuditLog model"""

    def setUp(self):
        """Set up test data"""
        self.admin = Employee.objects.create_superuser(
            username='admin',
            sAMAccountName='admin',
            password='admin123'
        )
        
        self.employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name_en='Mohamed',
            last_name_en='Khaled',
            employee_id='EMP001',
            national_id='123456789'
        )

    def test_create_ou_transfer_audit_log(self):
        """Test creating an OU transfer audit log"""
        log = OUTransferAuditLog.objects.create(
            employee=self.employee,
            old_ou='OU=IT,OU=New,DC=eissa,DC=local',
            new_ou='OU=HR,OU=New,DC=eissa,DC=local',
            changed_by=self.admin,
            status='success'
        )
        
        self.assertEqual(log.employee, self.employee)
        self.assertIsNotNone(log.changed_at)
        self.assertEqual(log.status, 'success')

    def test_audit_log_string_representation(self):
        """Test OU transfer log __str__ method"""
        log = OUTransferAuditLog.objects.create(
            employee=self.employee,
            old_ou='OU=IT,OU=New,DC=eissa,DC=local',
            new_ou='OU=Projects,OU=New,DC=eissa,DC=local',
            changed_by=self.admin,
            status='success'
        )
        
        self.assertIn(self.employee.get_full_name_en(), str(log))
        self.assertIn('Projects', str(log))

    def test_audit_log_with_error_message(self):
        """Test audit log storing error messages for failed transfers"""
        log = OUTransferAuditLog.objects.create(
            employee=self.employee,
            old_ou='OU=IT,OU=New,DC=eissa,DC=local',
            new_ou='OU=HR,OU=New,DC=eissa,DC=local',
            changed_by=self.admin,
            status='failed',
            error_message='Connection timeout'
        )
        
        self.assertEqual(log.status, 'failed')
        self.assertEqual(log.error_message, 'Connection timeout')

    def test_audit_log_ordering(self):
        """Test audit logs are ordered by most recent first"""
        log1 = OUTransferAuditLog.objects.create(
            employee=self.employee,
            old_ou='OU=IT,OU=New,DC=eissa,DC=local',
            new_ou='OU=HR,OU=New,DC=eissa,DC=local',
            changed_by=self.admin,
            status='success'
        )
        
        log2 = OUTransferAuditLog.objects.create(
            employee=self.employee,
            old_ou='OU=HR,OU=New,DC=eissa,DC=local',
            new_ou='OU=Projects,OU=New,DC=eissa,DC=local',
            changed_by=self.admin,
            status='success'
        )
        
        logs = list(OUTransferAuditLog.objects.all())
        self.assertEqual(logs[0].id, log2.id)
        self.assertEqual(logs[1].id, log1.id)


class LDAPBackendTests(TestCase):
    """Test cases for LDAP authentication backend"""

    def setUp(self):
        """Set up test data"""
        self.backend = LDAPBackend()
        self.mock_request = Mock()
        
        self.ad_user_data = {
            'sAMAccountName': 'khaled',
            'displayName': 'Mohamed Khaled',
            'mail': 'khaled@eissa.local',
            'telephoneNumber': '110030',
            'department': 'IT',
            'title': 'Developer',
            'distinguishedName': 'CN=khaled,OU=IT,OU=New,DC=eissa,DC=local',
            'organizational_unit': 'OU=IT,OU=New',
        }
        
        # Create a test employee
        self.employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            password='testpass123',
            first_name_en='Mohamed',
            last_name_en='Khaled'
        )

    def test_authenticate_without_credentials(self):
        """Test authentication without credentials fails"""
        result = self.backend.authenticate(self.mock_request, username=None, password=None)
        self.assertIsNone(result)

    def test_authenticate_without_password(self):
        """Test authentication without password fails"""
        result = self.backend.authenticate(self.mock_request, username='khaled', password=None)
        self.assertIsNone(result)

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_successful(self, mock_auth_ad):
        """Test successful LDAP authentication"""
        mock_auth_ad.return_value = self.ad_user_data
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='password123'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result.sAMAccountName, 'khaled')

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_fails_ad(self, mock_auth_ad):
        """Test LDAP authentication failure"""
        mock_auth_ad.return_value = None
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='wrongpassword'
        )
        
        self.assertIsNone(result)

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_ad_success_but_not_in_db(self, mock_auth_ad):
        """Test authentication succeeds in AD but user not in DB"""
        mock_auth_ad.return_value = {
            **self.ad_user_data,
            'sAMAccountName': 'newuser'
        }
        
        result = self.backend.authenticate(
            self.mock_request,
            username='newuser',
            password='password123'
        )
        
        # Should return None because user doesn't exist in DB
        self.assertIsNone(result)

    def test_extract_user_attributes(self):
        """Test extracting LDAP attributes"""
        mock_entry = Mock()
        mock_entry.sAMAccountName = 'khaled'
        mock_entry.displayName = 'Mohamed Khaled'
        mock_entry.mail = 'khaled@eissa.local'
        mock_entry.telephoneNumber = '110030'
        mock_entry.department = 'IT'
        mock_entry.title = 'Developer'
        mock_entry.distinguishedName = 'CN=khaled,OU=IT,OU=New,DC=eissa,DC=local'
        
        attributes = self.backend._extract_user_attributes(mock_entry)
        
        self.assertEqual(attributes['sAMAccountName'], 'khaled')
        self.assertEqual(attributes['mail'], 'khaled@eissa.local')
        self.assertEqual(attributes['telephoneNumber'], '110030')

    def test_get_user(self):
        """Test get_user method"""
        retrieved = self.backend.get_user(self.employee.id)
        self.assertEqual(retrieved.id, self.employee.id)

    def test_get_user_invalid_id(self):
        """Test get_user with invalid ID returns None"""
        retrieved = self.backend.get_user(99999)
        self.assertIsNone(retrieved)


class LDAPUtilitiesTests(TestCase):
    """Test cases for LDAP utilities"""

    def test_available_ous_loaded(self):
        """Test that available OUs are loaded"""
        self.assertGreater(len(AVAILABLE_OUS), 0)
        self.assertIn('IT', AVAILABLE_OUS)
        self.assertIn('HR', AVAILABLE_OUS)

    def test_ou_display_names(self):
        """Test OU display names in English and Arabic"""
        it_ou = AVAILABLE_OUS['IT']
        self.assertEqual(it_ou[1], 'تكنولوجيا المعلومات')

    def test_get_available_ous(self):
        """Test getting available OUs"""
        ous = ldap_manager.get_available_ous()
        self.assertIsInstance(ous, dict)
        self.assertGreater(len(ous), 0)

    def test_get_ou_display_name_english(self):
        """Test getting OU display name in English"""
        name = ldap_manager.get_ou_display_name('IT', lang='en')
        self.assertEqual(name, 'OU=IT,OU=New')

    def test_get_ou_display_name_arabic(self):
        """Test getting OU display name in Arabic"""
        name = ldap_manager.get_ou_display_name('IT', lang='ar')
        self.assertEqual(name, 'تكنولوجيا المعلومات')

    def test_get_ou_display_name_invalid(self):
        """Test getting display name for invalid OU"""
        name = ldap_manager.get_ou_display_name('InvalidOU')
        self.assertIsNone(name)


class EmployeeAuthenticationIntegrationTests(TransactionTestCase):
    """Integration tests for authentication"""

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_creates_token_after_login(self, mock_auth_ad):
        """Test that user can be authenticated via Django's authenticate function"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            password='testpass123'
        )
        
        ad_data = {
            'sAMAccountName': 'khaled',
            'displayName': 'Mohamed Khaled',
            'mail': 'khaled@eissa.local',
            'telephoneNumber': '110030',
            'department': 'IT',
            'title': 'Developer',
            'distinguishedName': 'CN=khaled,OU=IT,OU=New,DC=eissa,DC=local',
            'organizational_unit': 'OU=IT,OU=New',
        }
        
        mock_auth_ad.return_value = ad_data
        
        user = authenticate(username='khaled', password='password123')
        self.assertIsNotNone(user)
        self.assertEqual(user.sAMAccountName, 'khaled')

    def test_session_persistence(self):
        """Test that authenticated user can be retrieved for sessions"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            password='testpass123'
        )
        
        backend = LDAPBackend()
        retrieved = backend.get_user(employee.id)
        
        self.assertEqual(retrieved.id, employee.id)
        self.assertEqual(retrieved.sAMAccountName, 'khaled')

    """Test cases for Employee model and manager"""

    def setUp(self):
        """Set up test data"""
        self.employee_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'employee_id': 'EMP001',
            'national_id': '123456789',
            'hire_date': date(2020, 1, 15),
            'department': 'IT',
            'job_title': 'Developer',
            'sAMAccountName': 'testuser',
            'userPrincipalName': 'testuser@eissa.local',
        }

    def test_create_employee_basic(self):
        """Test creating a basic employee"""
        employee = Employee.objects.create_user(
            username=self.employee_data['username'],
            email=self.employee_data['email'],
            password='testpass123'
        )
        
        self.assertEqual(employee.username, self.employee_data['username'])
        self.assertEqual(employee.email, self.employee_data['email'])
        self.assertTrue(employee.check_password('testpass123'))
        self.assertTrue(employee.is_active_directory_user)

    def test_create_employee_with_all_fields(self):
        """Test creating employee with all fields"""
        employee = Employee.objects.create_user(
            **self.employee_data,
            password='testpass123'
        )
        
        self.assertEqual(employee.employee_id, self.employee_data['employee_id'])
        self.assertEqual(employee.national_id, self.employee_data['national_id'])
        self.assertEqual(employee.hire_date, self.employee_data['hire_date'])
        self.assertEqual(employee.department, self.employee_data['department'])
        self.assertEqual(employee.sAMAccountName, self.employee_data['sAMAccountName'])

    def test_create_superuser(self):
        """Test creating a superuser"""
        superuser = Employee.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='admin123'
        )
        
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_active)

    def test_create_superuser_without_is_staff(self):
        """Test that superuser requires is_staff=True"""
        with self.assertRaises(ValueError) as context:
            Employee.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin123',
                is_staff=False
            )
        self.assertIn('is_staff=True', str(context.exception))

    def test_employee_string_representation(self):
        """Test employee __str__ method"""
        employee = Employee.objects.create_user(
            username='john_doe',
            first_name='John',
            last_name='Doe'
        )
        
        expected_str = "John Doe (john_doe)"
        self.assertEqual(str(employee), expected_str)

    def test_employee_full_name_english(self):
        """Test get_full_name method"""
        employee = Employee.objects.create_user(
            username='john_doe',
            first_name='John',
            last_name='Doe'
        )
        
        self.assertEqual(employee.get_full_name(), 'John Doe')

    def test_employee_full_name_fallback(self):
        """Test get_full_name fallback to username when name not set"""
        employee = Employee.objects.create_user(username='john_doe')
        self.assertEqual(employee.get_full_name(), 'john_doe')

    def test_employee_full_name_arabic(self):
        """Test get_full_name_ar method"""
        employee = Employee.objects.create_user(
            username='hamed',
            first_name='Hamed',
            last_name='El-Sayed',
            first_name_ar='حامد',
            last_name_ar='السيد'
        )
        
        self.assertEqual(employee.get_full_name_ar(), 'حامد السيد')

    def test_ad_attributes_json_storage(self):
        """Test storing AD attributes in JSON field"""
        employee = Employee.objects.create_user(
            username='testuser',
            email='test@example.com'
        )
        
        ad_attrs = {
            'email': 'test@eissa.local',
            'phone': '110030',
            'displayName': 'Test User'
        }
        
        employee.update_ad_attributes(ad_attrs)
        employee.refresh_from_db()
        
        self.assertEqual(employee.ad_attributes_json['email'], 'test@eissa.local')
        self.assertEqual(employee.ad_attributes_json['phone'], '110030')

    def test_get_ad_email(self):
        """Test retrieving ad email from attributes"""
        employee = Employee.objects.create_user(
            username='testuser',
            email='local@example.com'
        )
        
        employee.ad_attributes_json = {'email': 'ad@eissa.local'}
        employee.save()
        
        self.assertEqual(employee.get_ad_email(), 'ad@eissa.local')

    def test_get_ad_phone(self):
        """Test retrieving ad phone from attributes"""
        employee = Employee.objects.create_user(username='testuser')
        
        employee.ad_attributes_json = {'phone': '110030'}
        employee.save()
        
        self.assertEqual(employee.get_ad_phone(), '110030')

    def test_employee_manager_relationship(self):
        """Test manager-subordinate relationships"""
        manager = Employee.objects.create_user(
            username='manager',
            first_name='Manager',
            last_name='User'
        )
        
        subordinate = Employee.objects.create_user(
            username='subordinate',
            first_name='Sub',
            last_name='User',
            manager=manager
        )
        
        self.assertEqual(subordinate.manager, manager)
        self.assertIn(subordinate, manager.subordinates.all())

    def test_unique_constraints(self):
        """Test unique constraints on key fields"""
        employee1 = Employee.objects.create_user(
            username='user1',
            employee_id='EMP001',
            sAMAccountName='user1',
            national_id='123456789'
        )
        
        # Should raise IntegrityError
        with self.assertRaises(Exception):
            Employee.objects.create_user(
                username='user2',
                employee_id='EMP001',  # Duplicate
            )

    def test_update_ad_attributes_updates_sync_time(self):
        """Test that update_ad_attributes updates ad_last_sync"""
        employee = Employee.objects.create_user(username='testuser')
        
        initial_sync = employee.ad_last_sync
        
        employee.update_ad_attributes({'test': 'value'})
        employee.refresh_from_db()
        
        self.assertIsNotNone(employee.ad_last_sync)
        if initial_sync:
            self.assertGreater(employee.ad_last_sync, initial_sync)

    def test_natural_key_retrieval(self):
        """Test get_by_natural_key method"""
        employee = Employee.objects.create_user(
            username='john_doe',
            first_name='John',
            last_name='Doe'
        )
        
        retrieved = Employee.objects.get_by_natural_key('john_doe')
        self.assertEqual(retrieved.id, employee.id)

    def test_queryset_ordering(self):
        """Test that employees are ordered by last_name, first_name"""
        Employee.objects.create_user(username='user1', first_name='Zara', last_name='Smith')
        Employee.objects.create_user(username='user2', first_name='Alice', last_name='Smith')
        Employee.objects.create_user(username='user3', first_name='Bob', last_name='Jones')
        
        employees = list(Employee.objects.all())
        
        # Should be ordered: Jones Bob, Smith Alice, Smith Zara
        self.assertEqual(employees[0].last_name, 'Jones')
        self.assertEqual(employees[1].first_name, 'Alice')
        self.assertEqual(employees[2].first_name, 'Zara')

    """Test cases for LDAP authentication backend"""

    def setUp(self):
        """Set up test data"""
        self.backend = LDAPBackend()
        self.mock_request = Mock()
        
        self.ad_user_data = {
            'sAMAccountName': 'khaled',
            'userPrincipalName': 'khaled@eissa.local',
            'displayName': 'Mohamed Khaled',
            'cn': 'Mohamed Khaled',
            'mail': 'khaled@eissa.local',
            'telephoneNumber': '110030',
            'department': 'IT',
            'title': 'Developer',
            'distinguishedName': 'CN=khaled,OU=IT,OU=New,DC=eissa,DC=local',
            'organizational_unit': 'IT,New'
        }

    def test_authenticate_without_credentials(self):
        """Test authentication without username or password fails"""
        result = self.backend.authenticate(self.mock_request, username=None, password=None)
        self.assertIsNone(result)

    def test_authenticate_without_username(self):
        """Test authentication without username fails"""
        result = self.backend.authenticate(self.mock_request, username=None, password='test')
        self.assertIsNone(result)

    def test_authenticate_without_password(self):
        """Test authentication without password fails"""
        result = self.backend.authenticate(self.mock_request, username='khaled', password=None)
        self.assertIsNone(result)

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_successful(self, mock_auth_ad):
        """Test successful LDAP authentication"""
        mock_auth_ad.return_value = self.ad_user_data
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='password123'
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result.username, 'khaled')
        self.assertEqual(result.sAMAccountName, 'khaled')

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_fails(self, mock_auth_ad):
        """Test LDAP authentication failure"""
        mock_auth_ad.return_value = None
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='wrongpassword'
        )
        
        self.assertIsNone(result)

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_creates_new_employee(self, mock_auth_ad):
        """Test that authentication creates new employee if not exists"""
        mock_auth_ad.return_value = self.ad_user_data
        
        # Ensure employee doesn't exist
        Employee.objects.filter(sAMAccountName='khaled').delete()
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='password123'
        )
        
        self.assertIsNotNone(result)
        employee = Employee.objects.get(sAMAccountName='khaled')
        self.assertEqual(employee.username, 'khaled')
        self.assertTrue(employee.is_active_directory_user)

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_updates_existing_employee(self, mock_auth_ad):
        """Test that authentication updates existing employee"""
        # Create existing employee
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled',
            first_name='Old',
            last_name='Name'
        )
        
        mock_auth_ad.return_value = self.ad_user_data
        
        result = self.backend.authenticate(
            self.mock_request,
            username='khaled',
            password='password123'
        )
        
        self.assertIsNotNone(result)
        employee.refresh_from_db()
        
        # Should have updated from AD data
        self.assertEqual(employee.job_title, 'Developer')
        self.assertEqual(employee.department, 'IT')

    def test_extract_user_attributes(self):
        """Test extracting user attributes from LDAP entry"""
        mock_entry = Mock()
        mock_entry.sAMAccountName = 'khaled'
        mock_entry.userPrincipalName = 'khaled@eissa.local'
        mock_entry.displayName = 'Mohamed Khaled'
        mock_entry.cn = 'khaled'
        mock_entry.mail = 'khaled@eissa.local'
        mock_entry.telephoneNumber = '110030'
        mock_entry.department = 'IT'
        mock_entry.title = 'Developer'
        mock_entry.distinguishedName = 'CN=khaled,OU=IT,OU=New,DC=eissa,DC=local'
        
        attributes = self.backend._extract_user_attributes(mock_entry)
        
        self.assertEqual(attributes['sAMAccountName'], 'khaled')
        self.assertEqual(attributes['mail'], 'khaled@eissa.local')
        self.assertEqual(attributes['telephoneNumber'], '110030')
        self.assertIn('IT', attributes['organizational_unit'])

    def test_extract_user_attributes_with_missing_fields(self):
        """Test extracting attributes when some fields are missing"""
        mock_entry = Mock()
        mock_entry.sAMAccountName = 'khaled'
        mock_entry.userPrincipalName = None
        mock_entry.displayName = None
        mock_entry.cn = 'khaled'
        mock_entry.mail = None
        mock_entry.telephoneNumber = None
        mock_entry.department = None
        mock_entry.title = None
        mock_entry.distinguishedName = 'CN=khaled,DC=eissa,DC=local'
        
        attributes = self.backend._extract_user_attributes(mock_entry)
        
        self.assertEqual(attributes['sAMAccountName'], 'khaled')
        self.assertIsNone(attributes['userPrincipalName'])
        self.assertIsNone(attributes['mail'])

    def test_get_or_create_employee_creates_new(self):
        """Test _get_or_create_employee creates new employee"""
        Employee.objects.filter(sAMAccountName='khaled').delete()
        
        employee = self.backend._get_or_create_employee('khaled', self.ad_user_data)
        
        self.assertIsNotNone(employee)
        self.assertEqual(employee.sAMAccountName, 'khaled')
        self.assertTrue(employee.is_active_directory_user)

    def test_get_or_create_employee_parses_display_name(self):
        """Test that display name is parsed into first and last name"""
        Employee.objects.filter(sAMAccountName='khaled').delete()
        
        employee = self.backend._get_or_create_employee('khaled', self.ad_user_data)
        
        self.assertEqual(employee.first_name, 'Mohamed')
        self.assertEqual(employee.last_name, 'Khaled')

    def test_get_or_create_employee_updates_ad_attributes(self):
        """Test that AD attributes are stored"""
        Employee.objects.filter(sAMAccountName='khaled').delete()
        
        employee = self.backend._get_or_create_employee('khaled', self.ad_user_data)
        
        self.assertEqual(employee.ad_attributes_json['email'], 'khaled@eissa.local')
        self.assertEqual(employee.ad_attributes_json['phone'], '110030')

    def test_get_user(self):
        """Test get_user method"""
        employee = Employee.objects.create_user(
            username='khaled',
            sAMAccountName='khaled'
        )
        
        retrieved = self.backend.get_user(employee.id)
        self.assertEqual(retrieved.id, employee.id)

    def test_get_user_invalid_id(self):
        """Test get_user with invalid ID returns None"""
        retrieved = self.backend.get_user(99999)
        self.assertIsNone(retrieved)


class EmployeeAuthenticationIntegrationTests(TransactionTestCase):
    """Integration tests for Employee authentication"""

    @patch('core.auth_backends.LDAPBackend._authenticate_ad')
    def test_authenticate_function_with_ldap(self, mock_auth_ad):
        """Test that user can be authenticated via Django's authenticate function"""
        # Create employee in DB first
        employee = Employee.objects.create_user(
            username='testuser',
            sAMAccountName='testuser',
            employee_id='EMP_TEST',
            national_id='999999999',
            password='testpass123'
        )
        
        ad_data = {
            'sAMAccountName': 'testuser',
            'userPrincipalName': 'testuser@eissa.local',
            'displayName': 'Test User',
            'cn': 'testuser',
            'mail': 'test@eissa.local',
            'telephoneNumber': '12345',
            'department': 'IT',
            'title': 'Tester',
            'distinguishedName': 'CN=testuser,OU=IT,OU=New,DC=eissa,DC=local',
            'organizational_unit': 'IT,New'
        }
        
        mock_auth_ad.return_value = ad_data
        
        user = authenticate(username='testuser', password='password123')
        
        self.assertIsNotNone(user)
        self.assertEqual(user.sAMAccountName, 'testuser')

    def test_session_persistence(self):
        """Test that authenticated user can be retrieved from database"""
        employee = Employee.objects.create_user(
            username='testuser',
            password='testpass123',
            sAMAccountName='testuser'
        )
        
        # Retrieve by primary key (for session management)
        backend = LDAPBackend()
        retrieved = backend.get_user(employee.id)
        
        self.assertEqual(retrieved.id, employee.id)
        self.assertEqual(retrieved.username, 'testuser')

