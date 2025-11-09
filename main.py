from flask import Flask, abort, send_file, render_template, request
from dotenv import load_dotenv
from whitelist import *
from onedrive import *
from utils import *
import os
import io

load_dotenv()

client_id = os.getenv("AZURE_CLIENT_ID")
tenant_id = os.getenv("AZURE_TENANT_ID")
scopes = ["User.Read", "Files.Read"]

app = Flask(__name__)
acl = ACL.from_yaml(open("rules.yml", "r", encoding="utf-8"))

client = Client(scopes, client_id, tenant_id)
client.devicecode_login()

app.jinja_env.filters["human_timestamp"] = human_timestamp
app.jinja_env.filters["human_filesize"] = human_filesize

@app.context_processor
def inject_globals():
    principal = get_principal()
    can_expose = acl.can_access(principal, request.path)

    return dict(can_expose=can_expose)

def get_principal():
    try:
        auth_cookie = request.cookies.get("Authorization")

        if auth_cookie == None:
            return acl.get_group("everyone")

        username, password = auth_cookie.split(":", 1)
        user = acl.get_user(username)

        if user.password == password:
            return user
    except:
        pass

    return acl.get_group("everyone")

@app.route("/auth")
def auth():
    return render_template("auth.html")

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path: str):
    principal = get_principal()
    if not acl.can_access(principal, path):
        return abort(403)

    try:
        if path == "":
            file = client.get_root()
        else:
            file = client.get_file_by_path(path)
    except:
        return abort(404)

    if file.is_folder:
        files = [file for file in client.get_children(file.id) if acl.can_access(principal, file.path)]

        return render_template(
            "index.html",
            path=path,
            files=files
        )
    
    else:
        content = io.BytesIO(client.get_content(file.id))
        return send_file(
            content,
            download_name=file.name,
            mimetype=file.mimetype,
            as_attachment=True
        )

if __name__ == "__main__":
    app.run()