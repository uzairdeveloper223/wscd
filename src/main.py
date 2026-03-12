import sys
import ids
import chat
import asyncio

debug = False

try:
    for i in sys.argv:
        if sys.argv.index(i) == 0:
            continue
        if i == "-d" or i == "--debug":
            debug = True
        else:
            print(f"ERROR! Unknown argument '{i}'")
            exit(1)
except Exception:
    pass

if __name__ == "__main__":
    print("wscd (websockets chatroom daemon), copyright 2026 sirruserror under the BSD-3 clause")
    if ids.globserv:
        print(f"Globserver found at {ids.globserv}")
    else:
        print("No globserver found on localhost.")
        print("Start one with: python3 src/globserver/server.py")
        exit(1)
    room_id = input("Enter RoomID <year>-<region>-<4-digits> : ")
    if debug:
        print(f"DEBUG: ID entered: {room_id}")
    room_dict = ids.parse_room_id(room_id)
    if debug:
        print(f"DEBUG: ID Token: {room_dict}")
    if room_dict is None:
        print("ERROR! RoomID not valid")
        exit(1)
    tunnel = ids.room_id_tunnel(room_dict)
    if debug and tunnel:
        print(tunnel["link"])
    if tunnel is None:
        print("ERROR! Could not resolve room tunnel")
        exit(1)
    asyncio.run(chat.chat(tunnel))
    exit(0)
