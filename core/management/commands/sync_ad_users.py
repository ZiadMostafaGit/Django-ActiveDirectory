"""
Django management command to sync users from Active Directory to the database.

Usage:
    python manage.py sync_ad_users
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Employee
from core.ldap_utils import ldap_manager


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
            default=None,
            help='Specific OU/Container to sync from (e.g. "CN=Users"). If omitted, searches common containers.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 Starting AD user sync...'))
        
        try:
            target_ous = [options['ou']] if options['ou'] else ['OU=New', 'CN=Users', 'DC=ad,DC=worex,DC=com']
            
            created = 0
            updated = 0
            skipped = 0
            total_found = 0

            for ou_path in target_ous:
                self.stdout.write(f"\n🔍 Searching in: {ou_path}")
                ad_users = ldap_manager.sync_users_from_container(ou_path)
                
                if not ad_users:
                    self.stdout.write(self.style.WARNING(f'⚠️  No users found or error in {ou_path}'))
                    continue
                
                total_found += len(ad_users)
                for ad_user in ad_users:
                    sam_account = ad_user['sAMAccountName']
                    display_name = ad_user['displayName'] or ''
                    email = ad_user['mail'] or ''
                    title = ad_user['title'] or ''
                    department = ad_user['department'] or ''
                    
                    # Split name for DB fields
                    name_parts = display_name.split(' ')
                    given_name = name_parts[0] if name_parts else ''
                    surname = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

                    # Skip computer accounts or empty accounts
                    if not sam_account or sam_account.endswith('$') or 'Computer' in display_name:
                        skipped += 1
                        continue
                    
                    try:
                        employee, created_new = Employee.objects.get_or_create(
                            sAMAccountName=sam_account,
                            defaults={
                                'username': sam_account,
                                'email': email,
                                'first_name_en': given_name,
                                'last_name_en': surname,
                                'job_title': title,
                                'department': department,
                                'employee_id': f"AD-{sam_account}",
                                'national_id': f"AD-{sam_account}",
                            }
                        )
                        
                        if created_new:
                            self.stdout.write(self.style.SUCCESS(f"✅ Created: {sam_account} ({display_name})"))
                            created += 1
                        elif options['update']:
                            employee.first_name_en = given_name
                            employee.last_name_en = surname
                            employee.job_title = title
                            employee.department = department
                            employee.email = email
                            employee.save()
                            self.stdout.write(self.style.WARNING(f"🔄 Updated: {sam_account}"))
                            updated += 1
                        else:
                            skipped += 1
                            
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Error for {sam_account}: {str(e)}"))
                        skipped += 1
            
            # Summary
            self.stdout.write("\n" + "="*80)
            self.stdout.write(self.style.SUCCESS(f"✅ Sync completed!"))
            self.stdout.write(f"   Total found in AD: {total_found}")
            self.stdout.write(f"   Created: {created}")
            self.stdout.write(f"   Updated: {updated}")
            self.stdout.write(f"   Skipped: {skipped}")
            self.stdout.write(f"   Total in DB: {Employee.objects.filter(is_superuser=False).count()}")
            self.stdout.write("="*80)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            import traceback
            traceback.print_exc()

