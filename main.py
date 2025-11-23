from flask import Flask, abort, render_template, request, Response, send_file
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
        return render_template(
            "index.html",
            path=path,
            files=files
        )
    
    else:
        content = io.BytesIO(client.get_content(file.id))
        response = Response(content.getvalue(), mimetype=file.mimetype)
        response.headers["Content-Disposition"] = f"attachment; filename={file.name}"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

if __name__ == "__main__":
    app.run()