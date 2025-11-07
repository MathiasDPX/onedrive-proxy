from dotenv import load_dotenv
from onedrive import *
import os

load_dotenv()

client_id = os.getenv("AZURE_CLIENT_ID")
tenant_id = os.getenv("AZURE_TENANT_ID")
scopes = ["User.Read", "Files.Read"]

client = Client(scopes, client_id, tenant_id)
client.devicecode_login()

file = client.get_file_by_path("archives")

"""
children = client.get_children("01UU6ICI7ZCFRFWXAVKNE2ANM57B362RMS")
for item in children:
    print(f'{item["name"]}: {item["id"]}')
"""