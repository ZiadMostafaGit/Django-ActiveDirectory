"""
Django management command to sync users from Active Directory to the database.

Usage:
    python manage.py sync_ad_users
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from ldap3 import Server, Connection, SIMPLE, ALL
from core.models import Employee
import os


class Command(BaseCommand):
    help = 'Sync employees from Active Directory to the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing employees with AD data',
        )
        parser.add_argument(
            '--ou',
            type=str,
            default='OU=New',
            help='OU to sync users from (default: OU=New - searches all departments recursively)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 Starting AD user sync...'))
        
        try:
            # Connect to AD
            ad_server = os.getenv('AD_SERVER')
            ad_port = int(os.getenv('AD_PORT', 389))
            ad_base_dn = os.getenv('AD_BASE_DN')
            ad_domain = os.getenv('AD_DOMAIN')
            ad_admin = f"administrator@{ad_domain}"
            ad_password = os.getenv('AD_ADMIN_PASSWORD', 'P@ssw0rd')
            
            server = Server(ad_server, port=ad_port, use_ssl=False, get_info=ALL)
            conn = Connection(server, user=ad_admin, password=ad_password, authentication=SIMPLE)
            
            if not conn.bind():
                self.stdout.write(self.style.ERROR(f'❌ Failed to bind to AD: {conn.last_error}'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'✅ Connected to AD at {ad_server}:{ad_port}'))
            
            # Search for users in the specified OU
            search_base = f"{options['ou']},{ad_base_dn}"
            self.stdout.write(f"\n🔍 Searching for users in: {search_base}")
            
            conn.search(
                search_base=search_base,
                search_filter='(objectClass=user)',
                attributes=[
                    'sAMAccountName',
                    'displayName',
                    'givenName',
                    'sn',
                    'mail',
                    'telephoneNumber',
                    'title',
                    'department',
                    'distinguishedName'
                ]
            )
            
            if not conn.entries:
                self.stdout.write(self.style.WARNING(f'⚠️  No users found in {search_base}'))
                return
            
            created = 0
            updated = 0
            skipped = 0
            
            self.stdout.write(f"\n📝 Found {len(conn.entries)} users in AD\n")
            
            for entry in conn.entries:
                sam_account = entry.sAMAccountName.value if entry.sAMAccountName else None
                display_name = entry.displayName.value if entry.displayName else ''
                given_name = entry.givenName.value if entry.givenName else ''
                surname = entry.sn.value if entry.sn else ''
                email = entry.mail.value if entry.mail else ''
                phone = entry.telephoneNumber.value if entry.telephoneNumber else ''
                title = entry.title.value if entry.title else ''
                department = entry.department.value if entry.department else ''
                
                # Skip computer accounts
                if 'Computer' in display_name or sam_account.endswith('$'):
                    skipped += 1
                    continue
                
                # Skip if no sAMAccountName
                if not sam_account:
                    skipped += 1
                    continue
                
                try:
                    employee, created_new = Employee.objects.get_or_create(
                        sAMAccountName=sam_account,
                        defaults={
                            'username': sam_account,
                            'email': email if email else '',
                            'first_name_en': given_name,
                            'last_name_en': surname,
                            'job_title': title,
                            'department': department,
                            'employee_id': f"AD-{sam_account}",
                            'national_id': f"AD-{sam_account}",
                        }
                    )
                    
                    if created_new:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ Created: {sam_account} ({given_name} {surname}) - {department or 'N/A'}"
                            )
                        )
                        created += 1
                    elif options['update']:
                        # Update existing employee with AD data
                        employee.first_name_en = given_name
                        employee.last_name_en = surname
                        employee.job_title = title
                        employee.department = department
                        employee.email = email if email else ''
                        employee.save()
                        self.stdout.write(
                            self.style.WARNING(
                                f"🔄 Updated: {sam_account} ({given_name} {surname}) - {department or 'N/A'}"
                            )
                        )
                        updated += 1
                    else:
                        skipped += 1
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Error creating {sam_account}: {str(e)}")
                    )
                    skipped += 1
            
            conn.unbind()
            
            # Summary
            self.stdout.write("\n" + "="*80)
            self.stdout.write(self.style.SUCCESS(f"✅ Sync completed!"))
            self.stdout.write(f"   Created: {created}")
            self.stdout.write(f"   Updated: {updated}")
            self.stdout.write(f"   Skipped: {skipped}")
            self.stdout.write(f"   Total in DB: {Employee.objects.filter(is_superuser=False).count()}")
            self.stdout.write("="*80)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            import traceback
            traceback.print_exc()
