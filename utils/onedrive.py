import msal
import requests
import os
from datetime import datetime
from typing import List
from utils.formatters import *
from urllib.parse import quote


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
            parse_date(data.get("createdDateTime")) if data.get("createdDateTime") else None,
            parse_date(data.get("lastModifiedDateTime")) if data.get("lastModifiedDateTime") else None
        )

        if data.get("file"):
            inst.mimetype = data["file"].get("mimeType", "application/octet-stream") or data["file"].get("mimetype", "application/octet-stream")

        return inst


class Client:
    def __init__(self, scopes: List[str], client_id: str, tenant_id: str,
                 graph_base="https://graph.microsoft.com/v1.0"):

        self.scopes = scopes
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.graph_base = graph_base
        self.session = requests.Session()

        # Backwards-compat: keep aliases used elsewhere in the repo
        self._session = self.session
        self._graph_base = self.graph_base

        # MSAL token cache
        self.cache_path = ".token_cache.json"
        self.token_cache = msal.SerializableTokenCache()

        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r") as f:
                try:
                    self.token_cache.deserialize(f.read())
                except Exception:
                    # ignore corrupt cache
                    pass

        self.app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self.token_cache
        )

    def _set_token(self, token):
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        # keep alias in sync
        self._session = self.session

    def _save_cache(self):
        try:
            with open(self.cache_path, "w") as f:
                f.write(self.token_cache.serialize())
        except Exception:
            # Best-effort; don't break the app on cache write failures
            pass

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

    def _ensure_valid_token(self) -> bool:
        """
        Ensure a valid access token is available in session headers
        by calling acquire_token_silent (MSAL will use refresh token if needed).
        Returns True if token present/set, False otherwise.
        """
        accounts = self.app.get_accounts()
        if not accounts:
            return False

        result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
        if result and "access_token" in result:
            self._set_token(result["access_token"])
            self._save_cache()
            return True

        return False

    def _request(self, method: str, url: str, retry_on_401: bool = True, **kwargs):
        """
        Wrapper around session requests that ensures token is valid and retries once on 401.
        method: 'get', 'post', 'put', ...
        """
        # Try to silently ensure token before the request
        self._ensure_valid_token()

        func = getattr(self.session, method)
        res = func(url, **kwargs)

        if res.status_code == 401 and retry_on_401:
            # Try to refresh token and retry once
            if self._ensure_valid_token():
                res = func(url, **kwargs)

        res.raise_for_status()
        return res

    def get_children(self, item_id="root") -> List[File]:
        if item_id == "root":
            url = f"{self.graph_base}/me/drive/root/children"
        else:
            url = f"{self.graph_base}/me/drive/items/{item_id}/children"

        res = self._request("get", url)
        return [File.from_request(item) for item in res.json().get("value", [])]

    def get_file_by_id(self, item_id) -> File:
        url = f"{self.graph_base}/me/drive/items/{item_id}"
        res = self._request("get", url)
        return File.from_request(res.json())

    def get_file_by_path(self, path) -> File:
        safe_path = path.strip("/")
        # URL-encode each path component separately to preserve slashes
        encoded_path = "/".join(quote(part, safe="") for part in safe_path.split("/"))
        url = f"{self.graph_base}/me/drive/root:/{encoded_path}"
        res = self._request("get", url)
        return File.from_request(res.json())

    def get_root(self) -> File:
        url = f"{self.graph_base}/me/drive/root"
        res = self._request("get", url)
        return File.from_request(res.json())

    def get_content(self, item_id) -> bytes:
        url = f"{self.graph_base}/me/drive/items/{item_id}/content"
        res = self._request("get", url)
        return res.content
