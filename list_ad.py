from core.ldap_utils import ldap_manager
from ldap3 import ALL_ATTRIBUTES

def list_containers():
    conn = ldap_manager._get_connection()
    if not conn:
        print("Failed to connect")
        return
    
    base_dn = ldap_manager.ad_base_dn
    print(f"Searching containers in {base_dn}...")
    
    # Search for all containers and OUs
    conn.search(
        search_base=base_dn,
        search_filter='(|(objectClass=organizationalUnit)(objectClass=container))',
        attributes=['distinguishedName']
    )
    
    print("\nContainers/OUs found:")
    for entry in conn.entries:
        print(f"- {entry.distinguishedName}")
    
    # Search for any user with "ahmed" in the name or sAMAccountName
    print("\nSearching for users matching 'ahmed'...")
    conn.search(
        search_base=base_dn,
        search_filter='(&(objectClass=user)(|(sAMAccountName=*ahmed*)(displayName=*ahmed*)(cn=*ahmed*)))',
        attributes=['sAMAccountName', 'distinguishedName', 'displayName']
    )
    
    for entry in conn.entries:
        print(f"User: {entry.sAMAccountName} | DN: {entry.distinguishedName} | Display: {entry.displayName}")

    conn.unbind()

if __name__ == "__main__":
    list_containers()
