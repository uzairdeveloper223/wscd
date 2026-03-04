import requests
import re
import json

global globserv
globserv = "http://127.0.0.1:5000" # change this

def parse_room_id(id_string):
    pattern = r"^(\d{4})-([A-Z]{2})-(\d{4})$"

    match = re.match(pattern, id_string)

    if match:
        year, region, number = match.groups()
        return {
            "year": year,
            "region": region,
            "number": number
        }
    else:
        return None

def roomID_tunnel(roomid: dict):
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
