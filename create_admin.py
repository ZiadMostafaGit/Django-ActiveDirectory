#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Employee

try:
    admin = Employee.objects.create_superuser(
        username='admin',
        sAMAccountName='admin',
        password='admin123',
        email='admin@example.com'
    )
    print("✅ Admin superuser created successfully!")
    print("Username: admin")
    print("Password: admin123")
except Exception as e:
    print(f"⚠️  Error: {e}")
    # Try to update if already exists
    try:
        admin = Employee.objects.get(username='admin')
        admin.set_password('admin123')
        admin.save()
        print("✅ Admin password reset to: admin123")
    except:
        print("❌ Failed to create admin user")
