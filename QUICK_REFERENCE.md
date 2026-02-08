# Quick Reference Guide - AD Integration

## First Run - Setup Checklist

- [ ] Update `.env` with your AD server IP/hostname
- [ ] Verify AD_BASE_DN matches your domain (DC=eissa,DC=local)
- [ ] Set AD_DOMAIN to your domain name
- [ ] Test connection: `python manage.py sync_ad_users --ou "OU=New"` (just to test, doesn't create duplicates)
- [ ] Create superuser: `python manage.py createsuperuser`
- [ ] Run migrations: `python manage.py migrate`
- [ ] Start server: `python manage.py runserver`

---

## Common Commands

### Sync Users from AD

```bash
# Sync all users from OU=New and all departments
python manage.py sync_ad_users --ou "OU=New"

# Sync specific department (e.g., IT)
python manage.py sync_ad_users --ou "OU=IT,OU=New"

# Update existing users with latest AD data
python manage.py sync_ad_users --ou "OU=New" --update

# Show help
python manage.py sync_ad_users --help
```

### Django Shell - Test AD Connection

```bash
python manage.py shell

# Test connection
>>> from core.ldap_utils import ldap_manager
>>> user = ldap_manager.get_user_by_samaccount('khaledAD')
>>> print(user)  # Shows user data from AD

# Get list of available OUs
>>> from core.ldap_utils import AVAILABLE_OUS
>>> print(list(AVAILABLE_OUS.keys()))

# Test user OU
>>> ou = ldap_manager.get_user_ou('khaledAD')
>>> print(ou)

# Exit shell
>>> exit()
```

### Database Operations

```bash
# Create admin user
python manage.py createsuperuser

# View all employees
python manage.py shell
>>> from core.models import Employee
>>> for emp in Employee.objects.all():
...     print(f"{emp.sAMAccountName}: {emp.department}")

# Clear all employees and transfer logs (CAREFUL!)
python manage.py shell
>>> from core.models import Employee, OUTransferAuditLog
>>> OUTransferAuditLog.objects.all().delete()
>>> Employee.objects.filter(is_superuser=False).delete()
```

---

## Admin Panel Operations

### Access Admin

1. Start server: `python manage.py runserver`
2. Go to: `http://localhost:8000/admin/`
3. Login with superuser credentials

### Employee List View

- **Username**: AD sAMAccountName (from AD)
- **Email**: Real-time from AD
- **Phone**: Real-time from AD  
- **Current OU**: Real-time from AD
- **Department**: From database

### Transfer Employee to Different OU

1. Click "Employees"
2. Select employee(s) checkbox
3. Select action: **"Transfer selected employees to different OU"**
4. Choose target OU from dropdown
5. Click "Go"
6. Confirm action

✅ Check "OU Transfer Audit Log" to see transfer history

### View Transfer History

1. Click "OU Transfer Audit Logs"
2. Filter by:
   - Status (Success/Failed)
   - Date range
   - Employee
   - Department
3. Search by employee sAMAccountName or name

---

## Available OUs for Transfers

Use these exact names when transferring users:

| Department | Key |
|-----------|-----|
| Accountant | `Accountant` |
| Administrative Affairs | `AdministrativeAffairs` |
| Camera | `Camera` |
| Exhibit | `Exhibit` |
| HR | `HR` |
| IT | `IT` |
| Audit | `Audit` |
| Out Work | `OutWork` |
| Projects | `Projects` |
| Sales | `Sales` |
| Supplies | `Supplies` |
| Secretarial | `Secretarial` |

---

## REST API - Quick Examples

### Login

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"khaledAD","password":"your_ad_password"}'
```

Response (copy the `access` token):
```json
{
  "access": "eyJ0eXAiOiJKV1...",
  "refresh": "eyJ0eXAiOiJKV1...",
  "user": {...}
}
```

### Get User Profile

```bash
curl http://localhost:8000/api/employee/profile/ \
  -H "Authorization: Bearer {access_token}"
```

### List All Employees

```bash
curl http://localhost:8000/api/employees/ \
  -H "Authorization: Bearer {access_token}"
```

---

## Troubleshooting Quick Fixes

### "AD Server not configured"
→ Check `.env` file has `AD_SERVER` set

### "Failed to bind to AD"
→ Verify AD_SERVER, AD_PORT, and connectivity: `ping {AD_SERVER}`

### No users showing in admin
→ Run sync: `python manage.py sync_ad_users --ou "OU=New"`

### Transfer failed with "User not found"
→ User might not exist in AD. Verify in AD or try different username

### Email/Phone showing as "—" in admin
→ Those fields come from AD. Check user's AD attributes exist

### Port 8000 already in use
→ Kill previous server: `pkill -f runserver`

---

## File Structure

```
/home/ziad/activedir/
├── .env                          ← Configuration file (UPDATE THIS!)
├── .env.example                  ← Example template
├── PRODUCTION_SETUP.md           ← Full documentation
├── manage.py
├── config/
│   ├── settings.py               ← Django settings (reads from .env)
│   └── ...
├── core/
│   ├── models.py                 ← Employee & OUTransferAuditLog
│   ├── admin.py                  ← Admin interface
│   ├── views.py                  ← API endpoints
│   ├── serializers.py            ← API serializers
│   ├── ldap_utils.py             ← LDAP/AD utils (AVAILABLE_OUS defined here)
│   ├── auth_backends.py          ← AD authentication
│   ├── management/commands/
│   │   └── sync_ad_users.py      ← User sync command
│   └── ...
└── requirements.txt
```

---

## Changing to Different AD Server

1. Edit `.env`:
```env
AD_SERVER=new.ad.server.com
AD_PORT=389
AD_BASE_DN=DC=new,DC=domain
AD_DOMAIN=new.domain.com
```

2. If OUs are different, edit `core/ldap_utils.py` and update `AVAILABLE_OUS`

3. Test: `python manage.py sync_ad_users --ou "OU=New"`

4. Existing employees stay in DB, new ones will be added

---

## Performance Tips

### For Large User Base (1000+ employees)

1. Use `--update` flag sparingly (slower):
```bash
python manage.py sync_ad_users --ou "OU=New" --update
```

2. Sync specific departments instead of all:
```bash
python manage.py sync_ad_users --ou "OU=IT,OU=New"
```

3. Batch transfers in admin using bulk actions

### Database Optimization

- Indexes are created automatically on:
  - `employee_id`
  - `sAMAccountName`
  - `national_id`
  - `department`

- Audit logs are indexed on `(employee, -changed_at)` for fast retrieval

---

## Security Checklist - Production

- [ ] Change `SECRET_KEY` in `.env` to a random value
- [ ] Set `DEBUG=False` in `.env`
- [ ] Use `AD_USE_SSL=True` with `AD_PORT=636`
- [ ] Change admin path from `/admin/` (use middleware or webserver config)
- [ ] Set strong passwords in AD for admin accounts
- [ ] Enable HTTPS for the application
- [ ] Review and backup OUTransferAuditLog regularly
- [ ] Restrict API access with IP whitelisting
- [ ] Monitor authentication failures
- [ ] Keep employee data backups

---

## Need Help?

1. **AD Connection issues**: Check `.env` configuration
2. **Users not syncing**: Run `python manage.py sync_ad_users --ou "OU=New"`
3. **Transfer failures**: Check audit log for specific error message
4. **API errors**: Use Bearer token from login response
5. **Django errors**: Enable `DEBUG=True` and check server output

