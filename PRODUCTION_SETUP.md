# Active Directory Integration - Production Setup Guide

## Overview

This Django application is designed to work with **ANY Active Directory environment**. It requires only the AD server credentials and domain information to function. The application:

- ✅ Syncs employees from any AD structure
- ✅ Stores only essential DB data (names, IDs, titles)
- ✅ Fetches live AD data on every request (email, phone, OU, displayName)
- ✅ Enables OU transfers with full audit logging
- ✅ Uses LDAP authentication for real AD credentials
- ✅ Provides REST API with JWT tokens

---

## Configuration

Configure the application by setting environment variables in `.env` file:

### AD Server Configuration

```env
# Your AD server IP or hostname
AD_SERVER=192.168.1.100

# LDAP Port (389 standard, 636 for LDAPS/SSL)
AD_PORT=389

# Use SSL/TLS encryption (True/False)
AD_USE_SSL=False

# Base DN - where to start searching for users
# Format: DC=domain,DC=com
# Examples:
# - eissa.local: DC=eissa,DC=local
# - company.com: DC=company,DC=com
AD_BASE_DN=DC=eissa,DC=local

# Domain name (used for UPN format user@domain)
AD_DOMAIN=eissa.local
```

---

## OUs Configuration for eissa.local

The eissa.local AD has 12 departments under `OU=New` container:

| Key | OU Path | Arabic Name |
|-----|---------|-------------|
| `Accountant` | `OU=Accountant,OU=New` | المحاسبة |
| `AdministrativeAffairs` | `OU=Administrative Affairs,OU=New` | الشؤون الإدارية |
| `Camera` | `OU=Camera,OU=New` | الكاميرات |
| `Exhibit` | `OU=Exhibit,OU=New` | المعارض |
| `HR` | `OU=HR,OU=New` | الموارد البشرية |
| `IT` | `OU=IT,OU=New` | تكنولوجيا المعلومات |
| `Audit` | `OU=Audit,OU=New` | المراجعة |
| `OutWork` | `OU=Out Work,OU=New` | العمل الخارجي |
| `Projects` | `OU=Projects,OU=New` | المشاريع |
| `Sales` | `OU=Sales,OU=New` | المبيعات |
| `Supplies` | `OU=Supplies,OU=New` | المشتريات |
| `Secretarial` | `OU=Secretarial,OU=New` | السكرتارية |

These OUs are defined in `core/ldap_utils.py` in the `AVAILABLE_OUS` dictionary.

---

## Setup Instructions

### Step 1: Update Environment Variables

Edit `.env` file with your AD server details:

```bash
nano .env
```

Update:
```env
AD_SERVER=your.ad.server.com    # Your AD server
AD_PORT=389                      # Usually 389
AD_USE_SSL=False                 # Usually False for standard LDAP
AD_BASE_DN=DC=eissa,DC=local    # Your domain DN
AD_DOMAIN=eissa.local            # Your domain name
```

### Step 2: Sync Users from AD

```bash
# Sync all users from OU=New and all departments
python manage.py sync_ad_users --ou "OU=New"

# Or sync from a specific department
python manage.py sync_ad_users --ou "OU=IT,OU=New"

# Update existing employees with latest AD data
python manage.py sync_ad_users --ou "OU=New" --update
```

### Step 3: Access Admin Panel

1. Create a superuser:
```bash
python manage.py createsuperuser
```

2. Start the server:
```bash
python manage.py runserver
```

3. Access admin at: `http://localhost:8000/admin/`

4. Manage employees and perform OU transfers

---

## User Data from AD

When a user is synced, the application extracts:

| AD Attribute | Purpose | Storage |
|-------------|---------|---------|
| `sAMAccountName` | Windows login name | **DB (immutable link)** |
| `givenName` | First name | **DB** |
| `sn` | Last name | **DB** |
| `mail` | Email address | **AD (fetched on-demand)** |
| `telephoneNumber` | Phone number | **AD (fetched on-demand)** |
| `title` | Job title | **DB** |
| `department` | Department | **DB** |
| `displayName` | Full display name | **AD (fetched on-demand)** |
| `distinguishedName` | Full DN/OU path | **AD (for OU detection)** |

**Why split storage?** 
- AD data is fetched fresh on every request ensuring it's always in sync
- DB data is editable through the admin panel for local customization

---

## User Management Through Admin Panel

### View Employees

1. Navigate to `Admin > Employees`
2. See all synced employees from AD
3. Each employee shows:
   - **sAMAccountName** - Link to AD
   - **English Names** - From AD
   - **Job Title & Department** - From AD
   - **Email** - Real-time from AD
   - **Phone** - Real-time from AD
   - **Current OU** - Real-time from AD

### Transfer Employee Between OUs

1. Select employee(s) in the list
2. Choose action: "Transfer selected employees to different OU"
3. Select target OU (Accountant, HR, IT, Projects, etc.)
4. Confirm

The system will:
- Move the user in AD using `modify_dn` operation
- Create an audit log entry with timestamp
- Record success/failure status
- Display any errors

### Sync Data from AD

1. Select employee(s)
2. Choose action: "Sync OU information from Active Directory"
3. This refreshes the current OU data from AD

---

## OU Transfer Example

**From the documentation you provided:**

```
Old DN: CN=mohamed khaled,OU=projects,OU=New,DC=eissa,DC=local
New OU: OU=IT,OU=New,DC=eissa,DC=local

# The application performs this automatically:
conn.modify_dn(old_dn, 'CN=mohamed khaled', new_superior=new_ou)
```

The application handles all of this through the admin action or API.

---

## REST API

### Login with AD Credentials

```bash
POST /api/auth/login/
{
  "username": "khaledAD",
  "password": "your_ad_password"
}

Response:
{
  "access": "jwt_token",
  "refresh": "refresh_token",
  "user": {
    "id": 1,
    "username": "khaledAD",
    "email": "khaled@eissa.local",
    "first_name_en": "Khaled",
    "department": "ITSM",
    "job_title": "ITSM Engineer",
    "ad_data": {
      "email": "khaled@eissa.local",
      "phone": "110030",
      "display_name": "Khaled Shehab",
      "ou": "OU=projects,OU=New,DC=eissa,DC=local"
    }
  }
}
```

### Get Current User Profile

```bash
GET /api/employee/profile/
Headers: Authorization: Bearer {access_token}
```

### List All Employees

```bash
GET /api/employees/
Headers: Authorization: Bearer {access_token}
```

---

## Architecture Diagram

```
┌─────────────────────────────────────┐
│   Active Directory (eissa.local)    │
│   ├── OU=IT                         │
│   ├── OU=HR                         │
│   ├── OU=Projects                   │
│   └── ... (9 other departments)     │
└──────────────▲──────────────────────┘
               │
        LDAP Connection
               │
┌──────────────▼──────────────────────┐
│   Django Application                │
│   ├── sync_ad_users command         │
│   ├── LDAP authentication           │
│   ├── OU transfer logic             │
│   └── Admin interface               │
└──────────────▲──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   Database (SQL Server)             │
│   ├── Employee table                │
│   │   ├── sAMAccountName (link)     │
│   │   ├── English names             │
│   │   ├── Job title & department    │
│   │   └── IDs & dates               │
│   └── OUTransferAuditLog table      │
│       ├── Transfer history          │
│       ├── Status & errors           │
│       └── Timestamps                │
└─────────────────────────────────────┘
```

---

## Troubleshooting

### Connection Issues

**Error: "Failed to bind to AD"**
- Verify AD_SERVER and AD_PORT are correct
- Check network connectivity: `ping {AD_SERVER}`
- Verify username/password format in AD

**Error: "No users found in OU"**
- Check the OU path is correct
- Verify users exist in that OU
- Try searching from base DN: `python manage.py sync_ad_users --ou "OU=New"`

### Transfer Issues

**Error: "User transferred to X"** (actually successful)
- Check audit log confirms success
- Verify user's OU changed in AD

**Error: "OU 'X' not found in available list"**
- Use valid OU names from AVAILABLE_OUS table (above)
- Ensure spelling matches (case-sensitive keys)

### AD Data Not Showing

- Verify user was synced with AD data
- Check network connectivity to AD server
- Review application logs for LDAP errors

---

## For Different AD Environments

To use this application with a **different** Active Directory:

1. Update `.env` with your AD server details
2. If OUs are different, update `AVAILABLE_OUS` in `core/ldap_utils.py`
3. Run sync command: `python manage.py sync_ad_users`
4. Application will work seamlessly

**Examples for other AD domains:**

```env
# For company.com
AD_SERVER=ad.company.com
AD_PORT=389
AD_BASE_DN=DC=company,DC=com
AD_DOMAIN=company.com

# For custom internal domain
AD_SERVER=192.168.1.50
AD_PORT=389
AD_BASE_DN=DC=internal,DC=corp
AD_DOMAIN=internal.corp
```

---

## Security Notes

⚠️ **Important:**

1. **Never commit `.env` to version control** - contains credentials
2. **Use LDAPS (SSL)** in production - set `AD_USE_SSL=True` and `AD_PORT=636`
3. **Strongly hash passwords** - Django auto-hashes user passwords
4. **Limit admin access** - Only admins can perform OU transfers
5. **Monitor audit logs** - Review `OUTransferAuditLog` regularly
6. **Use environment variables** - Never hardcode AD credentials in code

---

## Testing

Run the test suite:

```bash
python manage.py test core

# With verbose output
python manage.py test core -v 2
```

All 30+ tests cover:
- ✅ Employee model operations
- ✅ AD authentication
- ✅ LDAP utilities
- ✅ OU transfers
- ✅ Audit logging
- ✅ API endpoints

---

## Support

For issues or questions:

1. Check application logs: `tail -f logs/application.log`
2. Enable debug mode in `.env`: `DEBUG=True`
3. Test LDAP connection directly in Django shell:
   ```bash
   python manage.py shell
   >>> from core.ldap_utils import ldap_manager
   >>> user = ldap_manager.get_user_by_samaccount('khaledAD')
   >>> print(user)
   ```

