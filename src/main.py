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
            printf(f"ERROR! Unkown argument '{i}'")
            exit(1)

except Exception:
    pass

if __name__ == "__main__":
    print("wscd (websockets chatroom daemon), copyright 2026 sirruserror under the BSD-3 clause")
    id = input("Enter RoomID <year>-<region>-<4-digits> : ")
    if debug == True:
        print(f"DEBUG: ID entered: {id}")
    room_dict = ids.parse_room_id(id)
    if debug == True:
        print(f"DEBUG: ID Token: {room_dict}")
    if room_dict == None:
        print("ERROR! RoomID not valid")
        exit(1)
    tunnel = ids.roomID_tunnel(room_dict)
    if debug == True:
        print(tunnel["link"])
    asyncio.run(chat.chat(tunnel))
    

    
