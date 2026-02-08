# System Architecture & Data Flow Diagrams

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    YOUR ACTIVE DIRECTORY                        │
│                    (eissa.local, any AD)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  OU=New                                                  │  │
│  │  ├── OU=IT (تكنولوجيا المعلومات)                        │  │
│  │  ├── OU=HR (الموارد البشرية)                           │  │
│  │  ├── OU=Projects (المشاريع)                            │  │
│  │  ├── OU=Sales (المبيعات)                               │  │
│  │  ├── OU=Accountant (المحاسبة)                          │  │
│  │  └── ... 7 more departments                             │  │
│  │                                                          │  │
│  │  Each user has:                                         │  │
│  │  - sAMAccountName (khaledAD)                           │  │
│  │  - mail (khaledAD@eissa.local)                         │  │
│  │  - telephoneNumber (110030)                            │  │
│  │  - displayName (Khaled Shehab)                         │  │
│  │  - title, department, etc.                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        LDAP Connection (Port 389/636)
                      │
         ┌────────────▼────────────────┐
         │  Connection Validation      │
         │  (administrator@eissa.local)│
         └────────────┬────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│               DJANGO APPLICATION                                │
│        /home/ziad/activedir                                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  config/settings.py                                      │  │
│  │  - AD_SERVER        = os.getenv('AD_SERVER')            │  │
│  │  - AD_PORT          = os.getenv('AD_PORT')              │  │
│  │  - AD_BASE_DN       = os.getenv('AD_BASE_DN')           │  │
│  │  - AD_DOMAIN        = os.getenv('AD_DOMAIN')            │  │
│  │  - AD_USE_SSL       = os.getenv('AD_USE_SSL')           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  core/ldap_utils.py (LDAPManager)                        │  │
│  │  - AVAILABLE_OUS: 12 departments configured              │  │
│  │  - get_user_by_samaccount()   - Fetch user from AD      │  │
│  │  - get_user_ou()              - Get current OU          │  │
│  │  - transfer_user_ou()         - Move user to new OU     │  │
│  │  - _get_connection()          - LDAP connection         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  core/models.py                                          │  │
│  │  - Employee:                                             │  │
│  │    ├── sAMAccountName = "khaledAD" (AD link)           │  │
│  │    ├── username, names (EN/AR) (from DB)               │  │
│  │    ├── employee_id, national_id (from DB)              │  │
│  │    ├── job_title, department (editable)                │  │
│  │    └── hire_date (editable)                            │  │
│  │  - OUTransferAuditLog: Full transfer history            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  core/admin.py (Admin Panel)                             │  │
│  │  - Employee list with live AD data:                      │  │
│  │    ├── Email (fetched live from AD)                      │  │
│  │    ├── Phone (fetched live from AD)                      │  │
│  │    ├── Display Name (fetched live from AD)               │  │
│  │    └── Current OU (fetched live from AD)                 │  │
│  │  - OU Transfer bulk action                               │  │
│  │  - Audit log viewer with filters                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  core/views.py (REST API)                                │  │
│  │  - POST   /api/auth/login/         (JWT auth)           │  │
│  │  - GET    /api/employee/profile/   (current user)       │  │
│  │  - GET    /api/employees/          (list with AD data)  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  core/auth_backends.py (LDAP Auth)                       │  │
│  │  - Validates user with AD credentials                    │  │
│  │  - Returns Employee object from DB                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
  ┌──────────────┐           ┌──────────────────┐
  │  Web Browser │           │  API Clients     │
  │  /admin/     │           │  Mobile/Desktop  │
  └──────────────┘           └──────────────────┘
        │                             │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   SQL Server Database       │
        │   /home/ziad/activedir      │
        │                             │
        │  Tables:                    │
        │  - core_employee            │
        │  - core_outransferauditlog  │
        │  - django_user              │
        │  - auth_group               │
        │  - ... (other Django tables)│
        └─────────────────────────────┘
```

---

## 2. User Authentication Flow

```
┌─────────────────┐
│  User Login      │
│  khaledAD / ****│
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  REST API: POST /api/auth/login/    │
│  Body: {username, password}          │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Django Authentication Pipeline      │
│  - Try configured backends           │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  LDAPBackend.authenticate()          │
│  - Build UPN: khaledAD@eissa.local  │
│  - Connect to AD                     │
│  - Attempt LDAP bind                 │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  AD Server Response                  │
│  ├─ Valid: Password correct          │
│  └─ Invalid: Password wrong / User not found
└────────┬─────────────────────────────┘
         │
    ┌────┴─────────────────┐
    │                      │
    ▼ (Success)           ▼ (Failure)
┌─────────────────┐   ┌──────────────┐
│ Check Employee  │   │ Return None  │
│ Exists in DB    │   │ (Auth fails) │
│ ├─ Yes: OK      │   └──────────────┘
│ └─ No: Create   │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Generate JWT Token                  │
│  - access_token (1 hour)             │
│  - refresh_token (7 days)            │
│  - user_id, username, email          │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  API Response                        │
│  {                                   │
│    "access": "eyJ0eXAi...",         │
│    "refresh": "eyJ0eXAi...",        │
│    "user": {                         │
│      "id": 1,                        │
│      "username": "khaledAD",         │
│      "email": "khaledAD@eissa.local",
│      "first_name_en": "Khaled",     │
│      "department": "ITSM",           │
│      "ad_data": {                    │
│        "email": "khaledAD@...",     │
│        "phone": "110030",            │
│        "display_name": "...",        │
│        "ou": "OU=Projects,..."       │
│      }                               │
│    }                                 │
│  }                                   │
└──────────────────────────────────────┘
```

---

## 3. OU Transfer Flow

```
┌──────────────────────────────────────┐
│  Admin Panel: Employee List          │
│  ┌──────────────┐                    │
│  │ ☑ khaledAD   │                    │
│  │ ☑ omar       │  Select employees  │
│  │ ☐ muhamed    │                    │
│  └──────────────┘                    │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Action: "Transfer to Different OU"  │
│                                      │
│  Select Target OU:                   │
│  [▼ Choose OU]                       │
│  ├─ Accountant (المحاسبة)            │
│  ├─ HR (الموارد البشرية)             │
│  ├─ IT (تكنولوجيا المعلومات)         │
│  ├─ Projects (المشاريع)              │
│  └─ ... 8 more                       │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  transfer_ou_action() in admin.py    │
│                                      │
│  For each selected employee:         │
│  1. Get current OU from AD           │
│  2. Get target OU path from config   │
│  3. Call ldap_manager.transfer()     │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  ldap_manager.transfer_user_ou()     │
│                                      │
│  Current DN:                         │
│  CN=khaledAD,OU=Projects,OU=New,    │
│  DC=eissa,DC=local                  │
│                                      │
│  Target OU:                          │
│  OU=IT,OU=New,DC=eissa,DC=local      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  LDAP modify_dn() Operation          │
│                                      │
│  connection.modify_dn(               │
│    current_dn,                       │
│    'CN=khaledAD',                    │
│    new_superior=                     │
│      'OU=IT,OU=New,DC=eissa,...'    │
│  )                                   │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Active Directory Updates            │
│                                      │
│  User moved from:                    │
│    OU=Projects,OU=New                │
│  to:                                 │
│    OU=IT,OU=New                      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  OUTransferAuditLog.create()         │
│                                      │
│  {                                   │
│    employee: khaledAD,               │
│    old_ou: "OU=Projects,OU=New,...", │
│    new_ou: "OU=IT,OU=New,...",      │
│    changed_by: admin,                │
│    changed_at: 2026-02-08 14:30:00, │
│    status: "success",                │
│    error_message: ""                 │
│  }                                   │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Admin Response                      │
│                                      │
│  ✅ "Transferred 2 employee(s)"      │
│                                      │
│  Admin can now view:                 │
│  - Updated current OU in list        │
│  - Transfer log entry                │
│  - Status: Success                   │
└──────────────────────────────────────┘
```

---

## 4. Data Retrieval Flow (Admin Panel)

```
┌──────────────────────────────────────┐
│  Admin Panel: GET /admin/core/emp... │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  EmployeeAdmin.list_display()        │
│  For each Employee in DB:            │
│  1. username (from DB) ✓             │
│  2. sAMAccountName (from DB) ✓       │
│  3. first_name_en (from DB) ✓        │
│  4. department (from DB) ✓           │
│  5. email → fetch from AD ⬇          │
│  6. phone → fetch from AD ⬇          │
│  7. display_name → fetch from AD ⬇   │
│  8. current_ou → fetch from AD ⬇     │
└────────┬─────────────────────────────┘
         │
    ┌────┴────┬────────┬────────┐
    │         │        │        │
    ▼         ▼        ▼        ▼
  (1-4)     (5)      (6)       (7)
         
  DB        AD Call  AD Call   AD Call
  ├─email  ├─phone  ├─display ├─OU
  ├─phone  │        │name     │
  └─OU     │        │         │

For each AD call:

  ┌──────────────────────────────┐
  │  ldap_manager.get_user...()  │
  │  Connect to AD               │
  │  Search for sAMAccountName   │
  │  Extract attributes          │
  │  Return value or "—"         │
  └──────────────────────────────┘

All calls happen in parallel (cached within request)

         │
         ▼
┌──────────────────────────────────────┐
│  Admin Panel HTML Table              │
│                                      │
│  Username │ sAMAccountName │ Email  │
│  khaledAD │ khaledAD │ k...@eissa... │
│  omar     │ omar │ omar@eissa...     │
│  muhamed  │ muhamed.matar │ m...@ei  │
│           │               │          │
│  Phone    │ Display Name │ Current OU
│  110030   │ Khaled Shehab│ Projects  │
│  112233   │ Omar Walid   │ IT        │
│  114455   │ Muhamed Matar│ Sales     │
└──────────────────────────────────────┘
```

---

## 5. User Sync Flow

```
┌──────────────────────────────────────┐
│  Command: python manage.py            │
│  sync_ad_users --ou "OU=New"         │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Load Environment Variables (.env)  │
│  - AD_SERVER: 192.168.1.xxx          │
│  - AD_PORT: 389                      │
│  - AD_BASE_DN: DC=eissa,DC=local     │
│  - AD_DOMAIN: eissa.local            │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Connect to AD                       │
│  - Server: 192.168.1.xxx:389         │
│  - Bind as: administrator@eissa.local│
│  - Using password from env           │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Search in AD                        │
│  - Base: OU=New,DC=eissa,DC=local   │
│  - Filter: (objectClass=user)        │
│  - Attributes: sAMAccountName,       │
│    givenName, sn, mail, phone, etc.  │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Results: Found 8 Users in AD        │
│  [                                   │
│    {sAMAccountName: khaledAD,        │
│     givenName: Khaled,               │
│     sn: Shehab,                      │
│     mail: khaledAD@eissa.local,      │
│     telephoneNumber: 110030},        │
│    {...},                            │
│    ...                               │
│  ]                                   │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  For Each User:                      │
│  1. Check if exists in DB            │
│     (match on sAMAccountName)        │
│     ├─ Exists: Skip (or --update)   │
│     └─ Not exists: Create            │
│  2. Set fields:                      │
│     ├─ sAMAccountName (from AD)     │
│     ├─ username = sAMAccountName    │
│     ├─ first_name_en = givenName    │
│     ├─ last_name_en = sn            │
│     ├─ job_title = title            │
│     ├─ department = department      │
│     ├─ employee_id = AD-sAMAccount  │
│     └─ national_id = AD-sAMAccount  │
│  3. Save to database                │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Summary                             │
│                                      │
│  ✅ Sync completed!                  │
│     Created: 5                       │
│     Updated: 0 (--update flag)       │
│     Skipped: 3 (already exist)       │
│     Total in DB: 8                   │
└──────────────────────────────────────┘
```

---

## 6. Configuration-to-Runtime Flow

```
        .env File (YOUR CREDENTIALS)
        ├─ AD_SERVER=192.168.1.xxx
        ├─ AD_PORT=389
        ├─ AD_BASE_DN=DC=eissa,DC=local
        ├─ AD_DOMAIN=eissa.local
        └─ AD_USE_SSL=False
        │
        ▼
    os.getenv() calls in settings.py
        │
        ▼
    config/settings.py AD_* variables set
        │
        ├─┬─┬─┬─┬─ Used by multiple components:
        │ │ │ │ │
        │ │ │ │ └─→ sync_ad_users.py (sync command)
        │ │ │ │
        │ │ │ └─→ auth_backends.py (LDAP auth)
        │ │ │
        │ │ └─→ admin.py (fetch live data)
        │ │
        │ └─→ views.py (API endpoints)
        │
        └─→ ldap_utils.py (LDAPManager)
        │
        ▼
    Django Application
        └─ Works with ANY Active Directory!

To use with different AD:
    1. Change .env values
    2. Optionally update AVAILABLE_OUS in ldap_utils.py
    3. Run: python manage.py sync_ad_users
    Done! ✅
```

---

## 7. Complete Request/Response Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│  User visits: http://localhost:8000/admin/                      │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
    ┌─────────────────┐
    │  Redirected to  │
    │  /admin/login/  │
    └────────┬────────┘
             │
             ▼
    ┌──────────────────┐
    │  Enters:         │
    │  Username: ziad  │
    │  Password: ****  │
    │  [Login]         │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │  POST /admin/login/ (Django)     │
    │  - Check credentials             │
    │  - Set session cookie            │
    │  - Redirect to /admin/           │
    └────────┬───────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │  GET /admin/                     │
    │                                  │
    │  Render admin home               │
    │  Show available apps:            │
    │  - Employees                     │
    │  - OU Transfer Audit Logs        │
    │  - Groups, Users, etc.           │
    └────────┬───────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────┐
    │  Click: Employees                            │
    │  GET /admin/core/employee/                   │
    └────────┬──────────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────┐
    │  EmployeeAdmin.list_view() with changelist   │
    │                                              │
    │  For each Employee object:                   │
    │  ├─ username (from DB) ✓                     │
    │  ├─ sAMAccountName (from DB) ✓               │
    │  ├─ first_name (from DB) ✓                   │
    │  ├─ get_ad_email()         ← LDAP fetch ⬇   │
    │  ├─ get_ad_phone()         ← LDAP fetch ⬇   │
    │  ├─ get_ad_display_name()  ← LDAP fetch ⬇   │
    │  └─ current_ou_display()   ← LDAP fetch ⬇   │
    │                                              │
    │  ┌──────────────────────────────────┐       │
    │  │ For each LDAP fetch:             │       │
    │  │ 1. Connect to AD                 │       │
    │  │ 2. Search for sAMAccountName     │       │
    │  │ 3. Extract attribute             │       │
    │  │ 4. Cache result (within request) │       │
    │  │ 5. Return value or "—"           │       │
    │  └──────────────────────────────────┘       │
    └────────┬──────────────────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────────┐
    │  HTML Rendered & Sent to Browser       │
    │                                        │
    │  <table>                               │
    │    <tr>                                │
    │      <td>khaledAD</td>                 │
    │      <td>khaledAD</td>                 │
    │      <td>Khaled</td>                   │
    │      <td>Shehab</td>                   │
    │      <td>khaledAD@eissa.local</td>     │
    │      <td>110030</td>                   │
    │      <td>Khaled Shehab</td>            │
    │      <td>Projects</td>                 │
    │    </tr>                               │
    │  </table>                              │
    │                                        │
    │  Actions Dropdown:                     │
    │  ☐ Transfer to OU                      │
    │  ☐ Sync OU from AD                     │
    │  [Go]                                  │
    └────────────────────────────────────────┘
```

---

## Summary

These diagrams show:

1. **Architecture** - How all components connect
2. **Authentication** - Login flow with AD validation
3. **OU Transfers** - Move users between departments
4. **Data Retrieval** - Fetching live AD data
5. **User Sync** - Importing users from AD
6. **Configuration** - How .env flows through app
7. **Request Cycle** - Complete user interaction

**Key takeaway:** Every operation traces back to configurable environment variables in `.env`

