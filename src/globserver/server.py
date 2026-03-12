from flask import Flask, request, jsonify, send_file, render_template_string
import json
import os
import signal
import sys
import io
import zipfile
from pycloudflared import try_cloudflare

app = Flask(__name__)

DATA_FILE = "globserver_data.json"
TUNNEL_URL = None

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

LINK_DATABASE = load_data()

def graceful_shutdown(signum, frame):
    save_data(LINK_DATABASE)
    print("\nGlobserver stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

DOWNLOAD_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wscd — Download Client</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0d1117; color: #c9d1d9;
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
        }
        .card {
            background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 40px; max-width: 600px; width: 90%;
        }
        h1 { color: #58a6ff; font-size: 28px; margin-bottom: 8px; }
        .subtitle { color: #8b949e; margin-bottom: 24px; }
        .step { background: #0d1117; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .step-num { color: #58a6ff; font-weight: bold; margin-bottom: 4px; }
        code { background: #1c2128; padding: 2px 8px; border-radius: 4px; color: #79c0ff; font-size: 14px; }
        .dl-btn {
            display: inline-block; background: #238636; color: white; padding: 12px 24px;
            border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;
            margin: 20px 0; transition: background 0.2s;
        }
        .dl-btn:hover { background: #2ea043; }
        .servers { margin-top: 20px; }
        .server-item { background: #0d1117; padding: 10px 16px; border-radius: 6px; margin: 6px 0; }
        .server-code { color: #58a6ff; font-weight: bold; }
        .info { color: #8b949e; font-size: 13px; margin-top: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>wscd</h1>
        <p class="subtitle">websockets chatroom daemon</p>
        <a href="/download" class="dl-btn">⬇ Download Client</a>
        <div class="step">
            <div class="step-num">Step 1</div>
            Download and unzip the client files
        </div>
        <div class="step">
            <div class="step-num">Step 2</div>
            Install dependencies: <code>pip install websockets</code>
        </div>
        <div class="step">
            <div class="step-num">Step 3</div>
            Run: <code>python3 main.py</code>
        </div>
        <div class="step">
            <div class="step-num">Step 4</div>
            Enter the room code to join a chatroom
        </div>
        <div class="servers">
            <strong>Active Rooms ({{ server_count }})</strong>
            {% for code, url in servers.items() %}
            <div class="server-item">
                <span class="server-code">{{ code }}</span>
            </div>
            {% endfor %}
            {% if server_count == 0 %}
            <div class="server-item">No rooms active yet</div>
            {% endif %}
        </div>
        <p class="info">Globserver: {{ tunnel_url }}</p>
        <p class="info" style="margin-top: 8px;">
            <a href="https://github.com/sirruserror/wscd" target="_blank"
               style="color: #58a6ff; text-decoration: none;">
             GitHub — sirruserror/wscd
            </a>
            &nbsp;|&nbsp; Open source under BSD-3
        </p>
    </div>
</body>
</html>
""" 

@app.route('/')
def index():
    return render_template_string(
        DOWNLOAD_PAGE,
        tunnel_url=TUNNEL_URL or "localhost",
        servers=LINK_DATABASE,
        server_count=len(LINK_DATABASE)
    )

@app.route('/download')
def download_client():
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    glob_url = TUNNEL_URL if TUNNEL_URL else "http://127.0.0.1:5000"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        ids_content = f'''import requests
import re

globserv = "{glob_url}"

def parse_room_id(id_string):
    pattern = r"^(\\d{{4}})-([A-Z]{{2}})-(\\d{{4}})$"
    match = re.match(pattern, id_string)
    if match:
        year, region, number = match.groups()
        return {{
            "year": int(year),
            "region": region,
            "number": int(number)
        }}
    return None

def room_id_tunnel(roomid: dict):
    payload = {{"id": roomid}}
    try:
        response = requests.post(globserv + "/get-link", json=payload)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("ERROR! Could not reach global server, check your internet and retry")
        exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Server returned an error: {{e}}")
        return None
    return response.json()
'''
        zf.writestr("wscd-client/ids.py", ids_content)

        for filename in ["main.py", "chat.py", "machine.py"]:
            filepath = os.path.join(src_dir, filename)
            if os.path.exists(filepath):
                zf.write(filepath, f"wscd-client/{filename}")

    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='wscd-client.zip')

@app.route('/get-link', methods=['POST'])
def get_link_by_id():
    data = request.get_json()
    id_dict = data.get("id")

    if not id_dict:
        return jsonify({"error": "No ID dictionary provided"}), 400

    try:
        formatted_id = f"{id_dict['year']}-{id_dict['region']}-{int(id_dict['number']):04d}"
    except KeyError as e:
        return jsonify({"error": f"Missing key in ID dict: {str(e)}"}), 400

    link = LINK_DATABASE.get(formatted_id)

    if link:
        return jsonify({"status": "success", "link": link}), 200
    return jsonify({"error": "ID not found"}), 404

@app.route("/add-server", methods=['POST'])
def add_server_id():
    data = request.get_json()
    idadd = data.get("id")

    if not idadd:
        return jsonify({"error": "No ID passed"}), 400

    tunnel = data.get("tunnel")

    if not tunnel:
        return jsonify({"error": "No tunnel passed"}), 400

    try:
        formatted_id = f"{idadd['year']}-{idadd['region']}-{int(idadd['number']):04d}"
    except KeyError as e:
        return jsonify({"error": f"Missing key in ID dict: {str(e)}"}), 400

    LINK_DATABASE[formatted_id] = tunnel
    save_data(LINK_DATABASE)
    return jsonify({"status": "success"}), 200

@app.route("/remove-server", methods=['POST'])
def remove_server_id():
    data = request.get_json()
    idrem = data.get("id")

    if not idrem:
        return jsonify({"error": "No ID passed"}), 400

    try:
        formatted_id = f"{idrem['year']}-{idrem['region']}-{int(idrem['number']):04d}"
    except KeyError as e:
        return jsonify({"error": f"Missing key in ID dict: {str(e)}"}), 400

    if formatted_id in LINK_DATABASE:
        del LINK_DATABASE[formatted_id]
        save_data(LINK_DATABASE)
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "ID not found"}), 404

@app.route("/servers", methods=['GET'])
def list_servers():
    return jsonify({"status": "success", "count": len(LINK_DATABASE), "servers": LINK_DATABASE}), 200

if __name__ == '__main__':
    print("Starting Globserver tunnel...")
    tunnel_result = try_cloudflare(5000)
    TUNNEL_URL = str(tunnel_result.tunnel)

    print(f"\n===== GLOBSERVER IS LIVE =====")
    print(f"Public URL: {TUNNEL_URL}")
    print(f"Download:   {TUNNEL_URL}")
    print(f"Local:      http://127.0.0.1:5000")
    print(f"==============================\n")
    print("Share the URL above with friends so they can download the client!\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
