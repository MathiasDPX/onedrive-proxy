from azure.identity import DeviceCodeCredential
from typing import List
from utils.formatters import *
import requests
import json
import os
from datetime import datetime, timedelta


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
        self.token_cache_file = ".token_cache.json"
    
    def devicecode_login(self):
        credential = DeviceCodeCredential(self.client_id, tenant_id=self.tenant_id)
        token = credential.get_token(*self.scopes).token
        self._set_token(token)
        # Store token for caching (DeviceCodeCredential returns access_token directly)
        self.token = {
            'access_token': token,
            'expires_at': (datetime.now() + timedelta(hours=1)).timestamp()
        }

    def _set_token(self, token):
        if isinstance(token, str):
            _headers = {"Authorization": f"Bearer {token}"}
        else:
            _headers = {"Authorization": f"Bearer {token.get('access_token', token)}"}
        self._session.headers.update(_headers)

    def save_token_to_cache(self):
        """Sauvegarde le token actuel dans un fichier cache"""
        if hasattr(self, 'token') and self.token:
            cache_data = {
                'access_token': self.token.get('access_token'),
                'refresh_token': self.token.get('refresh_token'),
                'expires_at': self.token.get('expires_at'),
                'token_type': self.token.get('token_type')
            }
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache_data, f)
    
    def load_token_from_cache(self):
        """Charge le token depuis le cache s'il existe et est valide"""
        if not os.path.exists(self.token_cache_file):
            return False
        
        try:
            with open(self.token_cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Vérifie si le token n'est pas expiré
            expires_at = cache_data.get('expires_at')
            if expires_at and datetime.now().timestamp() < expires_at - 300:  # 5 min de marge
                self.token = cache_data
                self._set_token(cache_data['access_token'])
                return True
            
            # Essaie de rafraîchir le token s'il est expiré
            if cache_data.get('refresh_token'):
                return self.refresh_token(cache_data['refresh_token'])
            
        except Exception as e:
            print(f"Erreur lors du chargement du cache: {e}")
        
        return False
    
    def refresh_token(self, refresh_token):
        """Rafraîchit le token d'accès avec le refresh token"""
        try:
            token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            
            payload = {
                'client_id': self.client_id,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
                'scope': ' '.join(self.scopes)
            }
            
            resp = requests.post(token_url, data=payload)
            resp.raise_for_status()
            
            token_data = resp.json()
            self.token = token_data
            self._set_token(token_data['access_token'])
            self.save_token_to_cache()
            return True
            
        except Exception as e:
            print(f"Erreur lors du rafraîchissement du token: {e}")
            return False
    
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
