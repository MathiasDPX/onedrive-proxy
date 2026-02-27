from flask import Flask, abort, render_template, request, Response, send_file, stream_with_context
from dotenv import load_dotenv
from utils.whitelist import *
from utils.onedrive import *
from utils.formatters import *
import bcrypt
import os
import io
from functools import lru_cache
from werkzeug.utils import secure_filename
import secrets
import requests
from mimetypes import guess_type
from urllib.parse import quote

load_dotenv()

client_id = os.getenv("AZURE_CLIENT_ID")
tenant_id = os.getenv("AZURE_TENANT_ID")
scopes = ["User.Read", "Files.Read", "Files.ReadWrite"]

dropbox_name = os.getenv("DROPBOX_NAME", "Dropbox")

app = Flask(__name__)
acl = ACL.from_yaml(open("rules.yml", "r", encoding="utf-8"))

cached_passwords = {}
client = Client(scopes, client_id, tenant_id)

try:
    print("Authenticating...")
    client.devicecode_login()
    print("Authentication successful.")
except Exception as e:
    print(f"Authentication failed: {e}")
    exit(1)

app.jinja_env.filters["human_timestamp"] = human_timestamp
app.jinja_env.filters["human_filesize"] = human_filesize

@app.context_processor
def inject_globals():
    principal = get_principal()
    principal_id = principal.name if hasattr(principal, 'name') else "everyone"
    
    # Get parent path
    path = request.path.strip('/')
    if path == '':
        can_expose = False
    else:
        parent_path = '/'.join(path.split('/')[:-1])
        can_expose = can_access_cached(principal_id, parent_path)

    return dict(can_expose=can_expose)

def check_password(password, userpwd):
    if password in cached_passwords:
        return password == cached_passwords[password]
    
    if bcrypt.checkpw(password.encode(), userpwd.encode()):
        cached_passwords[password] = password
        return True
    else:
        return False

def get_principal():
    try:
        auth_cookie = request.cookies.get("Authorization")

        if auth_cookie == None:
            return acl.get_group("everyone")

        username, password = auth_cookie.split(":", 1)
        user = acl.get_user(username)

        if check_password(password, user.password):
            return user
    except:
        pass

    return acl.get_group("everyone")

@app.route("/_/upload", methods=["POST"])
def upload_file():
    principal = get_principal()
    if principal == None or type(principal) == Group:
        return {"error": True, "message": "Forbidden"}
    
    if principal not in acl.get_group("dropbox").get_members():
        return {"error": True, "message": "Forbidden"}

    files = request.files.getlist("file")

    if not files:
        return {"error": True, "message": "No files found"}

    try:
        parent = client.get_root()
        parent_id = parent.id
    except Exception:
        return abort(500)

    uploaded = []

    for f in files:
        original = secure_filename(f.filename or "untitled")
        suffix = secrets.token_hex(2)  # 4 hex chars
        username = principal.name if hasattr(principal, 'name') else 'anonymous'
        target_name = f"{username}_{suffix}_{original}"

        url = f"{client._graph_base}/me/drive/items/{parent_id}:/{dropbox_name}/{target_name}:/content"

        try:
            resp = client._session.put(url, data=f.read())
            resp.raise_for_status()
            uploaded.append(target_name)
        except Exception as e:
            return Response(str(e), status=502)

    return {"error": False, "message": uploaded}, 201

@app.route("/favicon.ico")
def favicon():
    return send_file("static/favicon.ico")

@app.route("/_/dropbox")
def dropbox():
    return render_template("dropbox.html")

@app.route("/_/auth")
def auth():
    return render_template("auth.html")

@lru_cache(maxsize=256)
def can_access_cached(principal_id: str, path: str):
    """Cache ACL access decisions to avoid repeated lookups"""
    principal = acl.get_group(principal_id) if principal_id == "everyone" else acl.get_user(principal_id)
    return acl.can_access(principal, path)

def parse_range_header(range_header: str, file_size: int):
    """Parse HTTP Range header and return (start, end) tuple"""
    if not range_header or not range_header.startswith("bytes="):
        return 0, file_size - 1
    
    try:
        range_spec = range_header[6:]  # remove "bytes="
        if "-" not in range_spec:
            return 0, file_size - 1
        
        start_str, end_str = range_spec.split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        
        # ensure valid range
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        
        return start, end
    except:
        return 0, file_size - 1

def stream_file_content(file_id: str, start: int = 0, end: int = None, chunk_size: int = 8192):
    """Stream file content in chunks from OneDrive with Range support"""
    try:
        # Ensure token is valid before streaming
        client._ensure_valid_token()
        
        url = f"{client._graph_base}/me/drive/items/{file_id}/content"
        headers = client._session.headers.copy()
        
        # Add Range header if seeking
        if start > 0 or end:
            range_header = f"bytes={start}"
            if end:
                range_header += f"-{end}"
            else:
                range_header += "-"
            headers["Range"] = range_header
        
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk
    except Exception as e:
        print(f"Streaming error: {e}")
        yield f"Error streaming file: {str(e)}".encode()

def create_m3u8(files:list[File]):
    lines = []
    
    lines.append("#EXTM3U")
    lines.append("")
    for file in files:
        lines.append(f"#EXTINF:-1,{os.path.basename(file.path)}")
        lines.append(f"{file.path}")
        
    return "\n".join(lines)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path: str):
    principal = get_principal()
    principal_id = principal.name if hasattr(principal, 'name') else "everyone"
    
    if not can_access_cached(principal_id, path):
        return abort(403)

    try:
        if path == "":
            file = client.get_root()
        else:
            file = client.get_file_by_path(path)
    except Exception as e:
        print(e)
        return abort(404)

    if file.is_folder:
        files = [file for file in client.get_children(file.id) if can_access_cached(principal_id, file.path)]
        
        if "libvlc" in request.headers.get('User-Agent', '').lower():
            return create_m3u8(files)
        
        return render_template(
            "index.html",
            path=path,
            files=files
        )
    
    else:
        # Determine mimetype
        mimetype = file.mimetype if file.mimetype and file.mimetype != "application/octet-stream" else None
        if not mimetype:
            mimetype, _ = guess_type(file.name)
        if not mimetype:
            mimetype = "application/octet-stream"
        
        file_size = file.size if hasattr(file, 'size') and file.size else 0
        range_header = request.headers.get("Range")
        
        # Parse range request for seeking
        if range_header and file_size > 0:
            start, end = parse_range_header(range_header, file_size)
            content_length = end - start + 1
            
            response = Response(
                stream_with_context(stream_file_content(file.id, start, end)),
                mimetype=mimetype,
                status=206
            )
            response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            response.headers["Content-Length"] = str(content_length)
        else:
            response = Response(
                stream_with_context(stream_file_content(file.id)),
                mimetype=mimetype,
                status=200
            )
            if file_size > 0:
                response.headers["Content-Length"] = str(file_size)
        
        # Properly encode filename in Content-Disposition header to handle special characters
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file.name)}"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Accept-Ranges"] = "bytes"
        
        return response

if __name__ == "__main__":
    app.run()