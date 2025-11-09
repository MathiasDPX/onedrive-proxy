from azure.identity import DeviceCodeCredential
from typing import List
from utils import *
import requests


class File:
    def __init__(self, name, id, size, path, parent_id, is_folder, ctime, mtime):
        self.name = name
        self.id = id
        self.size = size
        self.path = path
        self.parent_id = parent_id
        self.is_folder = is_folder
        self.mimetype = None
        self.ctime = ctime
        self.mtime = mtime

    @classmethod
    def from_request(cls, data):
        parent_ref = data.get("parentReference") or {}
        if data.get("folder", None) == None:
            is_folder = False
        else:
            is_folder = True

        inst = cls(
            data["name"],
            data["id"],
            data.get("size", 0),
            convert_path(parent_ref.get("path", ""))+"/"+data["name"],
            parent_ref.get("id"),
            is_folder,
            parse_date(data["createdDateTime"]),
            parse_date(data["lastModifiedDateTime"])
        )

        if data.get("file") != None:
            inst.mimetype = data.get("file", {}).get("mimetype", "application/octet-stream")

        return inst

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

    def devicecode_login(self):
        credential = DeviceCodeCredential(self.client_id, tenant_id=self.tenant_id)
        token = credential.get_token(*self.scopes).token
        self._set_token(token)

    def _set_token(self, token):
        _headers = {"Authorization": f"Bearer {token}"}
        self._session.headers = _headers

    def get_content(self, item_id) -> bytes:
        url = f"{self._graph_base}/me/drive/items/{item_id}/content"
        return self._session.get(url).content

    def get_children(self, item_id="root") -> List[File]:
        if item_id == "root":
            url = f"{self._graph_base}/me/drive/root/children"
        else:
            url = f"{self._graph_base}/me/drive/items/{item_id}/children"

        resp = self._session.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        return [File.from_request(file) for file in data.get("value", [])]
    
    def get_file_by_id(self, item_id) -> File:
        url = f"{self._graph_base}/me/drive/items/{item_id}"
        resp = self._session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return File.from_request(data)


    def get_file_by_path(self, path) -> File:
        url = f"{self._graph_base}/me/drive/root:/{path}"
        resp = self._session.get(url)
        resp.raise_for_status()
        data = resp.json()

        return File.from_request(data)

    def get_root(self) -> File:
        url = f"{self._graph_base}/me/drive/root"
        resp = self._session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return File.from_request(data)
