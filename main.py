from dotenv import load_dotenv
from onedrive import *
import json
import os

load_dotenv()

client_id = os.getenv("AZURE_CLIENT_ID")
tenant_id = os.getenv("AZURE_TENANT_ID")
scopes = ["User.Read", "Files.Read"]

client = Client(scopes, client_id, tenant_id)

print(client.get_children())