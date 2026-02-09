# System Flow Documentation

This document describes the **complete data flow**, **authentication mechanisms**, **admin operations**, and **storage locations**.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clients                                 │
│  (Web Browser, Mobile App, API Client)                         │
└────┬────────────────────────┬─────────────────────┬────────────┘
     │                        │                     │
     │ HTTP(S)                │ API Calls           │ API Calls
     ↓                        ↓                     ↓
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Admin      │  │  Login API       │  │  Employee API    │
│   Interface  │  │  /api/auth/login/│  │  /api/employees/ │
│ :8000/admin/ │  │                  │  │  /api/profile/   │
└──────┬───────┘  └────────┬─────────┘  └────────┬─────────┘
       │                   │                     │
       └───────────────────┴─────────────────────┘
                           │
                   ┌───────▼────────┐
                   │   Django App   │
                   │   (Gunicorn)   │
                   └───┬────────┬───┘
                       │        │
         ┌─────────────┘        └──────────┐
         │                                 │
         ↓                                 ↓
    ┌─────────────────┐        ┌────────────────────┐
    │  SQL Server DB  │        │  Active Directory  │
    │  (Local Data)   │        │  (Live Data)       │
    └─────────────────┘        │  (LDAP Server)     │
                               └────────────────────┘
         • Employees            • User Attributes
         • Audit Logs           • Email, Phone, Title
         • OU Transfers         • Department, OU
                               • 20,000+ Objects
```

---

## 2. Authentication Flow

### 2.1 Local Admin Login (for admin panel access)

```
┌─────────────────────────────────────────────────────────────────┐
│             LOCAL ADMIN AUTHENTICATION FLOW                     │
└─────────────────────────────────────────────────────────────────┘

User visits: http://localhost:8000/admin/
                    ↓
User enters: username=admin, password=admin123
                    ↓
Django authenticates against local Employee model (database)
                    ↓
        ✓ Credentials match stored admin user
                    ↓
Session created & stored in Django session table
                    ↓
User gains access to admin panel @/admin/
```

**Key Points:**
- Local admin credentials stored in SQL Server (hashed password)
- No AD involvement in admin login
- Session persisted in database
- Admin created manually via Django createsuperuser

---

### 2.2 User Login via API (with AD credentials)

```
┌─────────────────────────────────────────────────────────────────┐
│           AD USER AUTHENTICATION FLOW (API)                     │
└─────────────────────────────────────────────────────────────────┘

POST /api/auth/login/
{
  "sAMAccountName": "khaledAD",
  "password": "his_password"
}
                    ↓
LDAPBackend.authenticate() called
                    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 1: Validate against ACTIVE DIRECTORY          │
├─────────────────────────────────────────────────────┤
│ • Connect to LDAP server (192.168.1.208:389)      │
│ • Build UPN: khaledAD@ad.worex.com                │
│ • Attempt bind with user credentials               │
│ • If fails → return None                           │
│ • If succeeds → continue to STEP 2                 │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 2: Search AD for user attributes               │
├─────────────────────────────────────────────────────┤
│ • Query: (sAMAccountName=khaledAD)                 │
│ • In: CN=Users,DC=ad,DC=worex,DC=com              │
│ • Extract: email, phone, OU, displayName           │
│ • Format OU from distinguished name                │
│ • Return user attributes                           │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 3: Find user in local database                │
├─────────────────────────────────────────────────────┤
│ • Query: Employee.objects.get(                     │
│          sAMAccountName="khaledAD")                │
│ • If not found → return None                       │
│ • If found → return Employee object                │
│   (User MUST exist in DB to login)                 │
└─────────────────────────────────────────────────────┘
                    ↓
✓ User authenticated
                    ↓
┌─────────────────────────────────────────────────────┐
│ STEP 4: Generate JWT Tokens                         │
├─────────────────────────────────────────────────────┤
│ • Create refresh token                             │
│ • Create access token (expires in 5 min)           │
│ • Return both tokens + Employee serialized data    │
└─────────────────────────────────────────────────────┘
                    ↓
Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc4...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc4...",
  "user": {
    "id": 1,
    "sAMAccountName": "khaledAD",
    "first_name_en": "khaled",
    "last_name_en": "shehab",
    "employee_id": "AD-khaledAD",
    "ad_data": {
      "email": "khaled@ad.worex.com",
      "phone": "123456",
      "display_name": "khaled shehab",
      "current_ou": "OU=IT,OU=New,DC=ad,DC=worex,DC=com"
    }
  }
}
```

**Key Flow Points:**
1. AD credentials validated against LDAP/AD server over network
2. User attributes fetched from AD (not stored in DB, fetched on-demand)
3. User MUST exist in local Employee table to proceed
4. JWT tokens issued for subsequent API requests
5. Access token has short expiration (typically 5 min); refresh token lasts longer

---

## 3. Admin Panel Operations Flow

### 3.1 Admin Viewing Employees

```
┌─────────────────────────────────────────────────────────────────┐
│        ADMIN VIEWING EMPLOYEE LIST                              │
└─────────────────────────────────────────────────────────────────┘

Admin visits /admin/core/employee/
                    ↓
Django loads all Employee records from SQL Server
                    ↓
For each employee displayed:
                    ↓
┌─────────────────────────────────────────────────────┐
│ Fetch Real-Time AD Data                             │
├─────────────────────────────────────────────────────┤
│ EmployeeAdmin.current_ou_display() → calls:        │
│ ldap_manager.get_user_ou(sAMAccountName)            │
│                                                     │
│ EmployeeAdmin.get_ad_email() → calls:              │
│ ldap_manager.get_user_by_samaccount(sAMAccountName)│
│                                                     │
│ EmployeeAdmin.get_ad_phone() → calls:              │
│ ldap_manager.get_user_by_samaccount(sAMAccountName)│
│                                                     │
│ EmployeeAdmin.get_ad_display_name() → calls:       │
│ ldap_manager.get_user_by_samaccount(sAMAccountName)│
└─────────────────────────────────────────────────────┘
                    ↓
Each call connects to AD LDAP server and searches
                    ↓
Display combines:
  • Database fields: first_name_en, last_name_en, employee_id, job_title
  • REAL-TIME AD fields: 📧 Email, ☎️ Phone, 📍 OU, 👤 Display Name
                    ↓
Admin sees complete employee profile
(DB data + live AD data)
```

**Example Admin View:**
```
Employee List

username          | sAMAccountName | First Name | Last Name | Department | 📍 Current OU (from AD)
─────────────────────────────────────────────────────────────────────────────────────────────────
khaledAD          | khaledAD       | khaled     | shehab    | IT         | OU=IT,OU=New
admin             | admin          | admin      | admin     | N/A        | Not found in OU
hussein           | hussein        | hussein    | —         | N/A        | OU=Worex
```

---

### 3.2 Admin Transferring Employee to Different OU

```
┌─────────────────────────────────────────────────────────────────┐
│        ADMIN TRANSFERRING EMPLOYEE OU                           │
└─────────────────────────────────────────────────────────────────┘

Admin selects 1+ employees
Admin clicks "Transfer selected employees to different OU"
                    ↓
Form displays available OUs:
  • Accountant
  • AdministrativeAffairs
  • Camera
  • Exhibit
  • HR
  • IT
  ... (12 total OUs)
                    ↓
Admin selects "HR"
Admin clicks "Go"
                    ↓
For each selected employee:
                    ↓
┌─────────────────────────────────────────────────────┐
│ TRANSFER OPERATION                                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 1. Get current OU from AD:                         │
│    ldap_manager.get_user_ou("khaledAD")            │
│    → "OU=IT,OU=New,DC=ad,DC=worex,DC=com"         │
│                                                     │
│ 2. Build new DN:                                    │
│    new_dn = "CN=khaledAD,OU=HR,OU=New,             │
│             DC=ad,DC=worex,DC=com"                │
│                                                     │
│ 3. Execute modify_dn in LDAP:                       │
│    connection.modify_dn(                            │
│        dn="CN=khaledAD,OU=IT,OU=New,...",         │
│        new_rdn="CN=khaledAD",                      │
│        new_superior="OU=HR,OU=New,DC=ad,..."     │
│    )                                                │
│                                                     │
│ 4. Result tracked in audit log:                    │
│    OUTransferAuditLog.create(                       │
│        employee=khaledAD,                          │
│        old_ou="OU=IT,OU=New,...",                 │
│        new_ou="OU=HR,OU=New,...",                 │
│        changed_by=admin_user,                      │
│        status="success" or "failed",               │
│        error_message=if_failed                     │
│    )                                                │
│                                                     │
└─────────────────────────────────────────────────────┘
                    ↓
Admin sees confirmation:
"Transferred 1 employee(s)"
                    ↓
Change recorded in database audit log
Employee's AD OU updated in Active Directory
```

---

## 4. Data Storage and Locations

### 4.1 SQL Server Database (Local Storage)

**Database:** `django_dev`

**Table: core_employee**
```
Column                 Type          Notes
──────────────────────────────────────────────────────────────
id                     INT           Primary key
username               VARCHAR(150)  Unique, used for login
sAMAccountName         VARCHAR(100)  Unique, links to AD
password               VARCHAR(128)  Hashed (Django passworder)
email                  VARCHAR(254)  Usually empty (from AD)
first_name_en          VARCHAR(150)  Editable, stored
last_name_en           VARCHAR(150)  Editable, stored
first_name_ar          VARCHAR(150)  Editable, stored (Arabic)
last_name_ar           VARCHAR(150)  Editable, stored (Arabic)
employee_id            VARCHAR(50)   Unique, editable
national_id            VARCHAR(20)   Unique, editable
job_title              VARCHAR(100)  Editable
department             VARCHAR(100)  Editable
hire_date              DATE          Editable
is_active              BOOLEAN       User enabled/disabled
is_staff               BOOLEAN       Can access admin
is_superuser           BOOLEAN       Full admin access
date_joined            DATETIME      Auto-set on creation
last_login             DATETIME      Auto-updated on login

Indexes: employee_id, sAMAccountName, national_id, department
Count: 21 records (after sync)
```

**Example Records:**
```
id | sAMAccountName | first_name_en | last_name_en | employee_id | is_staff | is_superuser
───┼────────────────┼───────────────┼──────────────┼─────────────┼──────────┼─────────────
1  | admin          | admin         | admin        | local_admin | ✓        | ✓
2  | khaledAD       | khaled        | shehab       | AD-khaledAD | ✗        | ✗
3  | hussein        | hussein       | —            | AD-hussein  | ✗        | ✗
4  | youssef_adel   | Youssef       | Adel         | AD-youssef  | ✗        | ✗
...
```

**Table: core_outransferauditlog**
```
Column          Type          Notes
─────────────────────────────────────────────────────────────
id              INT           Primary key
employee_id     INT           Foreign key → core_employee
old_ou          VARCHAR(500)  Previous OU DN
new_ou          VARCHAR(500)  New OU DN
changed_by_id   INT           Foreign key → core_employee (admin who did it)
changed_at      DATETIME      Auto-set on creation
status          VARCHAR(20)   'success', 'failed', 'pending'
error_message   TEXT          If status='failed'

Example:
id | employee_id | old_ou                  | new_ou                  | changed_by_id | status  | changed_at
───┼─────────────┼─────────────────────────┼─────────────────────────┼───────────────┼─────────┼──────────────
1  | 2           | OU=IT,OU=New,...        | OU=HR,OU=New,...        | 1             | success | 2026-02-09...
```

---

### 4.2 Active Directory (LDAP Server) — Live Data

**Server:** 192.168.1.208:389 (not SSL)
**Base DN:** DC=ad,DC=worex,DC=com
**Users Container:** CN=Users,DC=ad,DC=worex,DC=com

**User Attributes Fetched On-Demand:**
```
Attribute            Type        Example
──────────────────────────────────────────────────────────────
sAMAccountName       String      khaledAD
displayName          String      khaled shehab
mail                 String      khaled@ad.worex.com
telephoneNumber      String      +1234567890
title                String      Senior IT Engineer
department           String      Information Technology
distinguishedName    String      CN=khaledAD,OU=IT,OU=New,DC=ad,DC=worex,DC=com

Extracted from DN:
  organizational_unit  String      OU=IT,OU=New,DC=ad,DC=worex,DC=com
```

**Available OUs (Departments):**
```
English Name              | LDAP Path                        | Arabic Name
──────────────────────────┼──────────────────────────────────┼──────────────────
Accountant                | OU=Accountant,OU=New             | المحاسبة
AdministrativeAffairs     | OU=Administrative Affairs,OU=New | الشؤون الإدارية
Camera                    | OU=Camera,OU=New                 | الكاميرات
Exhibit                   | OU=Exhibit,OU=New                | المعارض
HR                        | OU=HR,OU=New                     | الموارد البشرية
IT                        | OU=IT,OU=New                     | تكنولوجيا المعلومات
Audit                     | OU=Audit,OU=New                  | المراجعة
OutWork                   | OU=Out Work,OU=New               | العمل الخارجي
Projects                  | OU=Projects,OU=New               | المشاريع
Sales                     | OU=Sales,OU=New                  | المبيعات
Supplies                  | OU=Supplies,OU=New               | المشتريات
Secretarial               | OU=Secretarial,OU=New            | السكرتارية
```

**Total Objects:**
- 20+ users (imported after successful syncs)
- 5 OUs found
- 50 total AD users (when searched from AD)

---

### 4.3 What's Stored WHERE (Summary Table)

| Data Type | Stored In | Fetched How | Editable | Updated When |
|-----------|-----------|-------------|----------|--------------|
| **sAMAccountName** | DB + AD | From creation | No (immutable) | Never |
| **Password (hash)** | DB only | Not sync'd | Set in Django | Admin/User updates |
| **Email** | AD only | LDAP query on-demand | In AD only | Managed in AD |
| **Phone** | AD only | LDAP query on-demand | In AD only | Managed in AD |
| **OU (Org Unit)** | AD only | LDAP query on-demand | Via transfer_ou() | Admin changes / sync |
| **Display Name** | AD only | LDAP query on-demand | In AD only | Managed in AD |
| **First/Last Name (EN)** | DB only | Direct column | Yes (admin) | Admin edits |
| **First/Last Name (AR)** | DB only | Direct column | Yes (admin) | Admin edits |
| **Employee ID** | DB only | Direct column | Yes (admin) | Admin edits |
| **National ID** | DB only | Direct column | Yes (admin) | Admin edits |
| **Job Title (DB)** | DB only | Direct column | Yes (admin) | Admin edits |
| **Department (DB)** | DB only | Direct column | Yes (admin) | Admin edits |
| **Hire Date** | DB only | Direct column | Yes (admin) | Admin edits |
| **Transfer History** | DB + Audit Log | Logged on action | No | Every OU transfer |

---

## 5. API Flow

### 5.1 Login and Get JWT Token

```
POST /api/auth/login/
Content-Type: application/json

{
  "sAMAccountName": "khaledAD",
  "password": "his_ad_password"
}

↓ Response (200 OK) ↓

{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": 2,
    "employee_id": "AD-khaledAD",
    "sAMAccountName": "khaledAD",
    "first_name_en": "khaled",
    "last_name_en": "shehab",
    "first_name_ar": "",
    "last_name_ar": "",
    "job_title": "",
    "department": "",
    "hire_date": null,
    "national_id": "AD-khaledAD",
    "username": "khaledAD",
    "ad_data": {
      "email": "khaledAD@ad.worex.com",
      "phone": "+1234567890",
      "display_name": "khaled shehab",
      "current_ou": "OU=IT,OU=New,DC=ad,DC=worex,DC=com"
    }
  }
}
```

### 5.2 Get User Profile (Authenticated)

```
GET /api/employee/profile/
Authorization: Bearer eyJ0eXA...

↓ Response (200 OK) ↓

{
  "id": 2,
  "employee_id": "AD-khaledAD",
  "sAMAccountName": "khaledAD",
  "username": "khaledAD",
  "first_name_en": "khaled",
  "last_name_en": "shehab",
  "first_name_ar": "",
  "last_name_ar": "",
  "job_title": "",
  "department": "",
  "ad_data": {
    "email": "khaledAD@ad.worex.com",
    "phone": "+1234567890",
    "display_name": "khaled shehab",
    "current_ou": "OU=IT,OU=New,DC=ad,DC=worex,DC=com"
  }
}
```

### 5.3 List All Employees (Authenticated)

```
GET /api/employees/
Authorization: Bearer eyJ0eXA...

↓ Response (200 OK) ↓

{
  "count": 20,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 2,
      "employee_id": "AD-khaledAD",
      "sAMAccountName": "khaledAD",
      "first_name_en": "khaled",
      "last_name_en": "shehab",
      "job_title": "",
      "department": "",
      "username": "khaledAD",
      "ad_data": {
        "email": "khaledAD@ad.worex.com",
        "phone": "+1234567890",
        "display_name": "khaled shehab",
        "current_ou": "OU=IT,OU=New,DC=ad,DC=worex,DC=com"
      }
    },
    ...
  ]
}
```

---

## 6. Data Flow During User Login (Complete Sequence)

```
1. User submits login form (sAMAccountName + password)
                    ↓
2. POST /api/auth/login/
                    ↓
3. LDAPBackend.authenticate() invoked
                    ↓
4. Connect to LDAP server (192.168.1.208:389)
                    ↓
5. Attempt bind as: khaledAD@ad.worex.com + password
                    ✓ Success → continue
                    ✗ Fail → return error
                    ↓
6. LDAP search: (sAMAccountName=khaledAD)
                    ↓
7. Fetch attributes: mail, telephoneNumber, title, department
                    ↓
8. Extract OU from distinguishedName
                    ↓
9. Query DB: Employee.objects.get(sAMAccountName='khaledAD')
                    ✓ Found → continue
                    ✗ Not found → authentication fails
                    ↓
10. Generate JWT tokens (access + refresh)
                    ↓
11. Return response with:
    • Access token (short-lived)
    • Refresh token (long-lived)
    • Employee data + AD data
                    ↓
12. Client stores tokens in localStorage/cookies
                    ↓
13. Subsequent API requests include:
    Authorization: Bearer <access_token>
```

---

## 7. Data Consistency & Real-Time Guarantees

### What's Always Fresh (Real-Time)
✅ Email, Phone, Display Name, Title, Department → **Downloaded from AD on every request**
✅ Current OU (Organizational Unit) → **Downloaded from AD on every admin view or API call**

### What's Cached (Static Until Updated)
📦 Employee ID, National ID → **Stored in DB, updated only by admin**
📦 First/Last Name (EN/AR) → **Stored in DB, updated only by admin**
📦 Job Title (DB copy), Department (DB copy) → **Stored in DB, admin editable**

### What's Permanent (Immutable)
🔒 sAMAccountName → **Can never change once set (unique constraint)**
🔒 Password (local admin only) → **Hashed, stored in DB**

---

## 8. Sync Command Flow (`python manage.py sync_ad_users`)

```
Entry: python manage.py sync_ad_users --ou 'CN=Users' (or other OU)
                    ↓
Environment variables read (can override with -e flags):
  • AD_SERVER
  • AD_PORT
  • AD_BASE_DN
  • AD_DOMAIN
  • AD_ADMIN_PASSWORD (or use CLI flag)
                    ↓
Connect to AD with admin credentials:
  • Bind as: administrator@ad.worex.com + password
                    ↓
Search AD for users:
  Filter: (objectClass=user)
  Base: CN=Users,DC=ad,DC=worex,DC=com (or optional --ou)
                    ↓
For each user found:
  └─ Extract: sAMAccountName, displayName, mail, etc.
  └─ Skip computer accounts (ends with $)
  └─ Create or update Employee record in DB
  └─ Log: ✅ Created: khaledAD
                    ↓
Summary output:
  Created: 20
  Updated: 0
  Skipped: 0
  Total in DB: 21
```

---

## 9. Summary: Where Data Flows

```
┌──────────────────┐
│  Active Directory│         Real-Time Read
│  (LDAP Server)   │────────────────────────────┐
│                  │  LDAP Connections on Each: │
│ • Email (email)  │    - Admin page view       │
│ • Phone (phone)  │    - API request           │
│ • OU             │    - Profile page          │
│ • Display Names  │    - Employee list         │
│ • 20,000+ users  │                            │
└──────────────────┘                            │
                                                ↓
                                        ┌──────────────┐
                                        │   Caching    │
                                        │   (If Used)  │
                                        └──────┬───────┘
                                               ↓
                                        ┌──────────────┐
                                        │  Serializer  │
                                        │  For Display │
                                        └──────┬───────┘
                                               ↓
                                        ┌──────────────────┐
                                        │ Returned to User │
                                        │"AD Data" section │
                                        └──────────────────┘

┌──────────────────────┐
│      SQL Server DB   │         Used By
│<br>• Employee list     │────────────────→ Admin interface
│ • Audit logs        │                   API endpoints
│ • Static employee   │← Updated By:      Django ORM
│   data              │  • Admin edits
│ • Names (EN/AR)     │  • Import sync
│ • Employee/Nat IDs  │  • OU transfers
│ • 21 employees      │
└──────────────────────┘
```

---

## 10. Key Takeaways

1. **Hybrid Model**: Database stores only editable/unique data; AD stores user attributes fetched on-demand
2. **Always Fresh**: Every admin page view or API call queries AD for latest email, phone, OU
3. **One Source of Truth for Auth**: AD is the authority; users must exist in DB to login
4. **Audit Trail**: All OU transfers logged in DB with timestamp, initiator, and success/failure
5. **Scalable**: No caching of AD data = no stale data, but requires AD connectivity
6. **Secure**: Passwords not stored locally (uses AD); admin password hashed; JWT for API

