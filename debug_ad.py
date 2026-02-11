import os
import sys
from ldap3 import Server, Connection, ALL, SIMPLE

# Configuration matching .env.docker.local
AD_SERVER = '192.168.1.208'
AD_PORT = 389
AD_USER = 'Administrator@ad.worex.com'
AD_PASSWORD = 'P@ssw0rd'

print(f"Connecting to {AD_SERVER}:{AD_PORT}...")

try:
    server = Server(AD_SERVER, port=AD_PORT, get_info=ALL, connect_timeout=5)
    print(f"Server object created. connecting...")
    
    conn = Connection(server, user=AD_USER, password=AD_PASSWORD, authentication=SIMPLE, receive_timeout=5)
    print("Attempting bind...")
    
    if not conn.bind():
        print(f"❌ Bind failed: {conn.result}")
        sys.exit(1)
        
    print("✅ Bind successful!")
    print("-" * 50)
    
    print("Server Info (RootDSE):")
    if server.info:
        print(f"Default Naming Context: {server.info.other.get('defaultNamingContext', ['Not found'])[0]}")
        print(f"Root Domain Naming Context: {server.info.other.get('rootDomainNamingContext', ['Not found'])[0]}")
        print(f"Naming Contexts: {server.info.naming_contexts}")
    else:
        print("Could not retrieve server info (RootDSE)")

    print("-" * 50)
    print("Searching for user 'Administrator' to find their DN...")
    
    # Search from the RootDSE's default naming context if available, otherwise try a broad search
    base_dn = server.info.other.get('defaultNamingContext', [''])[0] if server.info else ''
    
    if not base_dn:
        print("⚠️ No DefaultNamingContext found. Trying to search without base DN (might fail)...")
    
    conn.search(
        search_base=base_dn,
        search_filter='(sAMAccountName=Administrator)',
        attributes=['distinguishedName']
    )
    
    if conn.entries:
        print(f"✅ Found Administrator: {conn.entries[0].distinguishedName}")
        print(f"   => The correct Base DN should likely be: {','.join(str(conn.entries[0].distinguishedName).split(',')[1:])}")
    else:
        print("❌ Could not find Administrator user.")

    conn.unbind()

except Exception as e:
    print(f"❌ Error: {e}")
