from flask import Flask, abort, send_file
from dotenv import load_dotenv
from onedrive import *
import os
import io

load_dotenv()

client_id = os.getenv("AZURE_CLIENT_ID")
tenant_id = os.getenv("AZURE_TENANT_ID")
scopes = ["User.Read", "Files.Read"]

app = Flask(__name__)

client = Client(scopes, client_id, tenant_id)
client.devicecode_login()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path: str):
    try:
        if path == "":
            file = client.get_root()
        else:
            file = client.get_file_by_path(path)
    except Exception as e:
        return abort(404)

    if file.is_folder:
        return "<br>".join([f.name for f in client.get_children(file.id)])
    else:
        content = io.BytesIO(client.get_content(file.id))
        return send_file(content, download_name=file.name,mimetype=file.mimetype, as_attachment=True)

if __name__ == "__main__":
    app.run()