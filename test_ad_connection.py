"""
Test script to verify AD connection and explore OU structure
Run with: python test_ad_connection.py
"""

import os
import sys
from dotenv import load_dotenv
from ldap3 import Server, Connection, ALL, SIMPLE

# Load environment variables
load_dotenv()

AD_SERVER = os.getenv('AD_SERVER')
AD_PORT = int(os.getenv('AD_PORT', 389))
AD_USE_SSL = os.getenv('AD_USE_SSL', 'False').lower() == 'true'
AD_BASE_DN = os.getenv('AD_BASE_DN')
AD_DOMAIN = os.getenv('AD_DOMAIN')

print("=" * 80)
print("ACTIVE DIRECTORY CONNECTION TEST")
print("=" * 80)
print(f"\n📋 Configuration:")
print(f"   Server: {AD_SERVER}:{AD_PORT}")
print(f"   SSL/TLS: {AD_USE_SSL}")
print(f"   Base DN: {AD_BASE_DN}")
print(f"   Domain: {AD_DOMAIN}")

# Test 1: Basic server connection
print("\n" + "=" * 80)
print("TEST 1: Connecting to AD Server...")
print("=" * 80)

try:
    server = Server(
        AD_SERVER,
        port=AD_PORT,
        use_ssl=AD_USE_SSL,
        get_info=ALL
    )
    print("✅ Server object created successfully")
    print(f"   Server info: {server.info}")
except Exception as e:
    print(f"❌ Failed to create server object: {e}")
    sys.exit(1)

# Test 2: Anonymous bind
print("\n" + "=" * 80)
print("TEST 2: Attempting anonymous bind...")
print("=" * 80)

try:
    conn = Connection(server, raise_exceptions=True)
    conn.bind()
    print("✅ Anonymous bind successful")
    conn.unbind()
except Exception as e:
    print(f"⚠️  Anonymous bind failed: {e}")
    print("   (This is OK - we'll use authenticated bind)")

# Test 3: Admin bind
print("\n" + "=" * 80)
print("TEST 3: Testing admin authentication...")
print("=" * 80)

admin_upn = f"administrator@{AD_DOMAIN}"
print(f"   Attempting bind as: {admin_upn}")

try:
    conn = Connection(
        server,
        user=admin_upn,
        password="P@ssw0rd",
        authentication=SIMPLE,
        raise_exceptions=True
    )
    conn.bind()
    print("✅ Admin authentication successful!")
    
    # Test 4: Search for users
    print("\n" + "=" * 80)
    print("TEST 4: Searching for users...")
    print("=" * 80)
    
    conn.search(
        search_base=AD_BASE_DN,
        search_filter="(objectClass=user)",
        attributes=['sAMAccountName', 'displayName', 'mail', 'telephoneNumber']
    )
    
    print(f"✅ Found {len(conn.entries)} user(s):")
    for entry in conn.entries[:10]:  # Show first 10
        sam = entry.sAMAccountName if entry.sAMAccountName else "N/A"
        display = entry.displayName if entry.displayName else "N/A"
        print(f"   - {sam}: {display}")
    
    # Test 5: Search for OUs
    print("\n" + "=" * 80)
    print("TEST 5: Searching for Organizational Units (OUs)...")
    print("=" * 80)
    
    conn.search(
        search_base=AD_BASE_DN,
        search_filter="(objectClass=organizationalUnit)",
        attributes=['ou', 'distinguishedName']
    )
    
    print(f"✅ Found {len(conn.entries)} OU(s):")
    for entry in conn.entries:
        ou = entry.ou if entry.ou else "N/A"
        dn = entry.distinguishedName
        print(f"   - OU={ou}: {dn}")
    
    # Test 6: Search for users under specific OUs
    print("\n" + "=" * 80)
    print("TEST 6: Looking for 'New' container and employee OUs...")
    print("=" * 80)
    
    # First, try to find 'New' container
    conn.search(
        search_base=AD_BASE_DN,
        search_filter="(name=New)",
        attributes=['distinguishedName', 'objectClass']
    )
    
    if conn.entries:
        print("✅ Found 'New' container:")
        for entry in conn.entries:
            dn = entry.distinguishedName
            print(f"   DN: {dn}")
            
            # Now search for OUs under New
            new_dn = dn
            conn.search(
                search_base=new_dn,
                search_filter="(objectClass=organizationalUnit)",
                attributes=['ou', 'distinguishedName']
            )
            
            if conn.entries:
                print(f"\n   OUs under {new_dn}:")
                for ou_entry in conn.entries:
                    ou_name = ou_entry.ou if ou_entry.ou else "N/A"
                    print(f"      - {ou_name}")
    else:
        print("⚠️  'New' container not found at root level")
        print("   OUs might be located elsewhere")
    
    conn.unbind()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST COMPLETE - All checks passed! ✅")
print("=" * 80)
print("\n💡 Next steps:")
print("   1. Verify the OU structure above matches your expected layout")
print("   2. Update the AVAILABLE_OUS in core/ldap_utils.py with actual OU paths")
print("   3. Create a test employee in the admin panel")
print("   4. Test login with AD credentials")
print("=" * 80)
