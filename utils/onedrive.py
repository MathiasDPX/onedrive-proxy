import msal
import requests
import os
from datetime import datetime
from typing import List
from utils.formatters import *


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
        is_folder = "folder" in data

        inst = cls(
            data["name"],
            data["id"],
            data.get("size", 0),
            convert_path(parent_ref.get("path", "")) + "/" + data["name"],
            parent_ref.get("id"),
            is_folder,
            parse_date(data["createdDateTime"]),
            parse_date(data["lastModifiedDateTime"])
        )

        if data.get("file"):
            inst.mimetype = data["file"].get("mimetype", "application/octet-stream")

        return inst


class Client:
    def __init__(self, scopes: List[str], client_id: str, tenant_id: str,
                 graph_base="https://graph.microsoft.com/v1.0"):

        self.scopes = scopes
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.graph_base = graph_base
        self.session = requests.Session()

        # MSAL token cache
        self.cache_path = ".token_cache.json"
        self.token_cache = msal.SerializableTokenCache()

        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r") as f:
                self.token_cache.deserialize(f.read())

        self.app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self.token_cache
        )


    def _set_token(self, token):
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _save_cache(self):
        with open(self.cache_path, "w") as f:
            f.write(self.token_cache.serialize())

    def devicecode_login(self):
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result and "access_token" in result:
                self._set_token(result["access_token"])
                self._save_cache()
                return result


        flow = self.app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            raise Exception("Impossible d'initialiser le Device Code Flow")

        print(flow["message"])

        result = self.app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise Exception("Authentication failed: %s" % result.get("error_description"))

        self._set_token(result["access_token"])
        self._save_cache()

        return result


    def get_children(self, item_id="root") -> List[File]:
        if item_id == "root":
            url = f"{self.graph_base}/me/drive/root/children"
        else:
            url = f"{self.graph_base}/me/drive/items/{item_id}/children"

        res = self.session.get(url)
        res.raise_for_status()
        return [File.from_request(item) for item in res.json().get("value", [])]

    def get_file_by_id(self, item_id) -> File:
        url = f"{self.graph_base}/me/drive/items/{item_id}"
        res = self.session.get(url)
        res.raise_for_status()
        return File.from_request(res.json())

    def get_file_by_path(self, path) -> File:
        url = f"{self.graph_base}/me/drive/root:/{path}"
        res = self.session.get(url)
        res.raise_for_status()
        return File.from_request(res.json())

    def get_root(self) -> File:
        url = f"{self.graph_base}/me/drive/root"
        res = self.session.get(url)
        res.raise_for_status()
        return File.from_request(res.json())

    def get_content(self, item_id) -> bytes:
        url = f"{self.graph_base}/me/drive/items/{item_id}/content"
        res = self.session.get(url)
        res.raise_for_status()
        return res.content
