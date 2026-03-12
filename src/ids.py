import requests
import re
import json

LOCALHOST_URLS = ["http://127.0.0.1:5000", "http://localhost:5000"]

def detect_globserver():
    for url in LOCALHOST_URLS:
        try:
            r = requests.get(url + "/servers", timeout=2)
            if r.status_code == 200:
                return url
        except Exception:
            continue
    return None

globserv = detect_globserver()

def parse_room_id(id_string):
    pattern = r"^(\d{4})-([A-Z]{2})-(\d{4})$"
    match = re.match(pattern, id_string)
    if match:
        year, region, number = match.groups()
        return {
            "year": int(year),
            "region": region,
            "number": int(number)
        }
    return None

def room_id_tunnel(roomid: dict):
    if not globserv:
        print("ERROR! No globserver found on localhost.")
        print("Start one with: python3 src/globserver/server.py")
        exit(1)
    payload = {"id": roomid}
    try:
        response = requests.post(globserv + "/get-link", json=payload)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("ERROR! Could not reach global server, check your internet and retry")
        exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Server returned an error: {e}")
        return None
    return response.json()
