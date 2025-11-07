from azure.identity import DeviceCodeCredential
from typing import List
import requests
import os

class File:
    def __init__(self, name, id, mimetype, size, path, parent_id):
        self.name = name
        self.id = id
        self.mimetype = mimetype
        self.size = size
        self.path = path
        self.parent_id = parent_id

class Client:
    def __init__(self,
                 scopes: List[str],
                 client_id: str,
                 tenant_id: str,
                 graph_base: str = "https://graph.microsoft.com/v1.0"
                ):
        self.scopes = scopes
        self.client_id = client_id
        self.tenant_id = tenant_id
        
        self._graph_base = graph_base
        self._session = requests.session()

    def _devicecode_credential(self):
        credential = DeviceCodeCredential(self.client_id, tenant_id=self.tenant_id)
        token = credential.get_token(*self.scopes).token
        self._set_token(token)

    def _set_token(self, token):
        _headers = {"Authorization": f"Bearer {token}"}
        self._session.headers = _headers

    def get_content(self, item_id):
        url = f"{self._graph_base}/me/drive/items/{item_id}/content"
        return self._session.get(url).content


    def get_children(self, item_id="root"):
        if item_id == "root":
            url = f"{self._graph_base}/me/drive/root/children"
        else:
            url = f"{self._graph_base}/me/drive/items/{item_id}/children"
        return self._session.get(url).json()