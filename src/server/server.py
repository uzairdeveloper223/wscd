import asyncio
import websockets
import random
import json
import os
import time
import signal
import re
from datetime import date, datetime
from pycloudflared import try_cloudflare
import requests

GLOBSERVER = "http://127.0.0.1:5000"

CLIENTS = {}
USER_INFO = {}
ADMIN_IDS = set()
MOD_IDS = set()
BANNED_IDS = set()
MUTED_USERS = {}
CHAT_HISTORY = []
MAX_HISTORY = 100
MAX_NICKNAME_LENGTH = 32
MAX_MESSAGE_LENGTH = 500
RATE_LIMIT_MESSAGES = 5
RATE_LIMIT_WINDOW = 10
user_message_times = {}
DATA_FILE = "server_data.json"
connection_lock = asyncio.Lock()
dm_approved = set()
dm_pending = {}
dm_blocks = {}
pending_nick_change = {}
SERVER_MOTD = "Welcome to wscd and talktootuff doesn't talk tuff!"

def timestamp():
    return datetime.now().strftime("%H:%M")

def load_server_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return (
                    set(data.get('admin_ids', [])),
                    set(data.get('mod_ids', [])),
                    set(data.get('banned_ids', [])),
                    data.get('chat_history', [])
                )
        except (json.JSONDecodeError, ValueError):
            return set(), set(), set(), []
    return set(), set(), set(), []

def save_server_data():
    data = {
        'admin_ids': list(ADMIN_IDS),
        'mod_ids': list(MOD_IDS),
        'banned_ids': list(BANNED_IDS),
        'chat_history': CHAT_HISTORY[-MAX_HISTORY:]
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

ADMIN_IDS, MOD_IDS, BANNED_IDS, CHAT_HISTORY = load_server_data()

def get_user_id(websocket):
    return USER_INFO.get(websocket, {}).get("user_id")

def get_user_name(websocket):
    return USER_INFO.get(websocket, {}).get("name", "Unknown")

def is_admin(websocket):
    return get_user_id(websocket) in ADMIN_IDS

def is_mod(websocket):
    uid = get_user_id(websocket)
    return uid in MOD_IDS or uid in ADMIN_IDS

def is_valid_nickname(name):
    if not name or len(name) > MAX_NICKNAME_LENGTH:
        return False
    if not name.replace('_', '').replace('-', '').isalnum():
        return False
    return True

def check_rate_limit(user_id):
    current_time = time.time()
    if user_id not in user_message_times:
        user_message_times[user_id] = []

    user_message_times[user_id] = [
        t for t in user_message_times[user_id]
        if current_time - t < RATE_LIMIT_WINDOW
    ]

    if len(user_message_times[user_id]) >= RATE_LIMIT_MESSAGES:
        return False

    user_message_times[user_id].append(current_time)
    return True

def is_muted(user_id):
    if user_id not in MUTED_USERS:
        return False
    if time.time() >= MUTED_USERS[user_id]:
        del MUTED_USERS[user_id]
        return False
    return True

async def send_to_all(message):
    if CLIENTS:
        await asyncio.gather(
            *[client.send(message) for client in CLIENTS.keys()],
            return_exceptions=True
        )

async def send_system(websocket, message):
    try:
        await websocket.send(f"[SYSTEM] {message}")
    except websockets.exceptions.ConnectionClosed:
        pass

def find_user_ws(target_id):
    for ws, info in USER_INFO.items():
        if info["user_id"] == target_id:
            return ws
    return None

async def handle_command(websocket, message):
    if not message.startswith("/"):
        return False

    parts = message.split()
    cmd = parts[0].lower()
    args = parts[1:]
    user_is_admin = is_admin(websocket)
    user_is_mod = is_mod(websocket)

    if cmd == "/help":
        await send_system(websocket, "Available commands:")
        await send_system(websocket, "  /users - List connected users")
        await send_system(websocket, "  /nick <name> - Change your nickname")
        await send_system(websocket, "  /dm <id> <msg> - Send a direct message")
        await send_system(websocket, "  /accept <id> - Accept a DM request")
        await send_system(websocket, "  /decline <id> - Decline a DM request")
        await send_system(websocket, "  /cancel <id> - Cancel your DM request")
        await send_system(websocket, "  /block <id> - Block a user from DMing you")
        await send_system(websocket, "  /unblock <id> - Unblock a user")
        await send_system(websocket, "  /dms - List your DM conversations")
        await send_system(websocket, "  /help - Show this help")
        if user_is_mod:
            await send_system(websocket, "  /kick <id> - Kick a user")
            await send_system(websocket, "  /mute <id> <seconds> - Mute a user")
            await send_system(websocket, "  /settings - Server admin panel")
        if user_is_admin:
            await send_system(websocket, "  /ban <id> - Ban a user")
            await send_system(websocket, "  /unban <id> - Unban a user")
            await send_system(websocket, "  /clear - Clear chat history")
            await send_system(websocket, "  /makemod <id> - Promote to mod")
            await send_system(websocket, "  /removemod <id> - Demote from mod")
            await send_system(websocket, "  /makeadmin <id> - Promote to admin")
        return True

    if cmd == "/users":
        users_list = ""
        for ws, info in USER_INFO.items():
            uid = info["user_id"]
            name = info["name"]
            users_list += f"  {uid}: {name}\n"
        await send_system(websocket, "CONNECTED USERS")
        await send_system(websocket, users_list)
        return True

    if cmd == "/settings":
        if not user_is_mod:
            return False
        await send_system(websocket, f"Online: {len(CLIENTS)}")
        await send_system(websocket, f"History: {len(CHAT_HISTORY)}/{MAX_HISTORY}")
        await send_system(websocket, f"Banned: {len(BANNED_IDS)}")
        await send_system(websocket, f"Muted: {len(MUTED_USERS)}")
        users_list = ""
        for ws, info in USER_INFO.items():
            uid = info["user_id"]
            name = info["name"]
            roles = []
            if uid in ADMIN_IDS:
                roles.append("ADMIN")
            if uid in MOD_IDS:
                roles.append("MOD")
            if is_muted(uid):
                remaining = int(MUTED_USERS[uid] - time.time())
                roles.append(f"MUTED {remaining}s")
            role_str = f" [{', '.join(roles)}]" if roles else ""
            users_list += f"  {uid}: {name}{role_str}\n"
        await send_system(websocket, users_list)
        if BANNED_IDS:
            await send_system(websocket, f"Banned IDs: {', '.join(BANNED_IDS)}")
        return True

    if cmd == "/mute":
        if not user_is_mod:
            return False
        if len(args) < 2:
            await send_system(websocket, "Usage: /mute <user_id> <seconds>")
            return True
        target_id = args[0]
        if target_id == get_user_id(websocket):
            await send_system(websocket, "You can't mute yourself.")
            return True
        try:
            duration = int(args[1])
        except ValueError:
            await send_system(websocket, "Duration must be a number in seconds.")
            return True
        if duration < 1 or duration > 86400:
            await send_system(websocket, "Duration must be between 1 and 86400 seconds.")
            return True
        MUTED_USERS[target_id] = time.time() + duration
        target_ws = find_user_ws(target_id)
        if target_ws:
            target_name = get_user_name(target_ws)
            await send_system(target_ws, f"You have been muted for {duration} seconds.")
            await send_to_all(f"[SYSTEM] {target_name} has been muted for {duration}s.")
        else:
            await send_system(websocket, f"User not found, but mute applied to ID {target_id}.")
        return True

    if cmd == "/kick":
        if not user_is_mod:
            return False
        if not args:
            await send_system(websocket, "Usage: /kick <user_id>")
            return True
        target_id = args[0]
        if target_id == get_user_id(websocket):
            await send_system(websocket, "You can't kick yourself.")
            return True
        target_ws = find_user_ws(target_id)
        if target_ws:
            target_name = get_user_name(target_ws)
            await send_system(target_ws, "You have been kicked from the chat.")
            await target_ws.close()
            await send_to_all(f"[SYSTEM] {target_name} has been kicked.")
        else:
            await send_system(websocket, "User not found.")
        return True

    if cmd == "/ban":
        if not user_is_admin:
            return False
        if not args:
            await send_system(websocket, "Usage: /ban <user_id>")
            return True
        target_id = args[0]
        if target_id == get_user_id(websocket):
            await send_system(websocket, "You can't ban yourself.")
            return True
        BANNED_IDS.add(target_id)
        save_server_data()
        target_ws = find_user_ws(target_id)
        if target_ws:
            target_name = get_user_name(target_ws)
            await send_system(target_ws, "You have been banned from this chat.")
            await target_ws.close()
            await send_to_all(f"[SYSTEM] {target_name} has been banned.")
        else:
            await send_system(websocket, "User not found, but ID has been banned.")
        return True

    if cmd == "/unban":
        if not user_is_admin:
            return False
        if not args:
            await send_system(websocket, "Usage: /unban <user_id>")
            return True
        target_id = args[0]
        if target_id in BANNED_IDS:
            BANNED_IDS.remove(target_id)
            save_server_data()
            await send_system(websocket, f"User {target_id} has been unbanned.")
        else:
            await send_system(websocket, "User is not banned.")
        return True

    if cmd == "/makemod":
        if not user_is_admin:
            return False
        if not args:
            await send_system(websocket, "Usage: /makemod <user_id>")
            return True
        target_id = args[0]
        MOD_IDS.add(target_id)
        save_server_data()
        await send_system(websocket, f"User {target_id} is now a moderator.")
        await send_to_all(f"[SYSTEM] {target_id} has been promoted to moderator.")
        return True

    if cmd == "/removemod":
        if not user_is_admin:
            return False
        if not args:
            await send_system(websocket, "Usage: /removemod <user_id>")
            return True
        target_id = args[0]
        if target_id in MOD_IDS:
            MOD_IDS.remove(target_id)
            save_server_data()
            await send_system(websocket, f"User {target_id} is no longer a moderator.")
        else:
            await send_system(websocket, "User is not a moderator.")
        return True

    if cmd == "/makeadmin":
        if not user_is_admin:
            return False
        if not args:
            await send_system(websocket, "Usage: /makeadmin <user_id>")
            return True
        target_id = args[0]
        ADMIN_IDS.add(target_id)
        save_server_data()
        await send_system(websocket, f"User {target_id} is now an admin.")
        await send_to_all(f"[SYSTEM] {target_id} has been promoted to admin.")
        return True

    if cmd == "/dm":
        if len(args) < 2:
            await send_system(websocket, "Usage: /dm <user_id> <message>")
            return True
        sender_id = get_user_id(websocket)
        sender_name = get_user_name(websocket)
        target_id = args[0]
        dm_msg = " ".join(args[1:])
        target_ws = find_user_ws(target_id)
        if not target_ws:
            await send_system(websocket, "User not found or not online.")
            return True
        if target_id == sender_id:
            await send_system(websocket, "You can't DM yourself.")
            return True
        target_blocks = dm_blocks.get(target_id, set())
        pair = frozenset({sender_id, target_id})
        if pair in dm_approved:
            target_name = get_user_name(target_ws)
            await websocket.send(f"[{timestamp()}] [DM to {target_name}] {dm_msg}")
            if sender_id not in target_blocks:
                await target_ws.send(f"[{timestamp()}] [DM from {sender_name}] {dm_msg}")
        else:
            if sender_id in target_blocks:
                await websocket.send(f"[{timestamp()}] [DM to {get_user_name(target_ws)}] {dm_msg}")
                return True
            pending_key = (sender_id, target_id)
            reverse_key = (target_id, sender_id)
            if pending_key in dm_pending:
                await send_system(websocket, f"You already have a pending request to this user. /cancel {target_id} first.")
            elif reverse_key in dm_pending:
                await send_system(websocket, f"This user already sent you a DM request. Use /accept {target_id}.")
            else:
                dm_pending[pending_key] = dm_msg
                target_name = get_user_name(target_ws)
                await send_system(target_ws, f"{sender_name} ({sender_id}) wants to DM you. /accept {sender_id} or /decline {sender_id}")
                await send_system(websocket, f"DM request sent. Waiting for {target_name} to accept...")
        return True

    if cmd == "/accept":
        if not args:
            await send_system(websocket, "Usage: /accept <user_id>")
            return True
        accepter_id = get_user_id(websocket)
        sender_id = args[0]
        pending_key = (sender_id, accepter_id)
        if pending_key not in dm_pending:
            await send_system(websocket, "No pending DM request from that user.")
            return True
        pair = frozenset({sender_id, accepter_id})
        dm_approved.add(pair)
        pending_msg = dm_pending.pop(pending_key)
        sender_ws = find_user_ws(sender_id)
        sender_name = get_user_name(sender_ws) if sender_ws else "Unknown"
        accepter_name = get_user_name(websocket)
        await websocket.send(f"[{timestamp()}] [DM from {sender_name}] {pending_msg}")
        await send_system(websocket, f"DM from {sender_name} accepted. You can now /dm {sender_id} freely.")
        if sender_ws:
            await sender_ws.send(f"[{timestamp()}] [DM to {accepter_name}] {pending_msg}")
            await send_system(sender_ws, f"{accepter_name} accepted your DM. You can now /dm {accepter_id} freely.")
        return True

    if cmd == "/decline":
        if not args:
            await send_system(websocket, "Usage: /decline <user_id>")
            return True
        decliner_id = get_user_id(websocket)
        sender_id = args[0]
        pending_key = (sender_id, decliner_id)
        if pending_key not in dm_pending:
            await send_system(websocket, "No pending DM request from that user.")
            return True
        dm_pending.pop(pending_key)
        decliner_name = get_user_name(websocket)
        sender_ws = find_user_ws(sender_id)
        await send_system(websocket, f"DM request from {sender_id} declined.")
        if sender_ws:
            await send_system(sender_ws, f"{decliner_name} declined your DM request.")
        return True

    if cmd == "/cancel":
        if not args:
            await send_system(websocket, "Usage: /cancel <user_id>")
            return True
        sender_id = get_user_id(websocket)
        target_id = args[0]
        pending_key = (sender_id, target_id)
        if pending_key not in dm_pending:
            await send_system(websocket, "No pending DM request to that user.")
            return True
        dm_pending.pop(pending_key)
        await send_system(websocket, f"DM request to {target_id} cancelled.")
        target_ws = find_user_ws(target_id)
        if target_ws:
            sender_name = get_user_name(websocket)
            await send_system(target_ws, f"{sender_name} cancelled their DM request.")
        return True

    if cmd == "/block":
        if not args:
            await send_system(websocket, "Usage: /block <user_id>")
            return True
        blocker_id = get_user_id(websocket)
        target_id = args[0]
        if target_id == blocker_id:
            await send_system(websocket, "You can't block yourself.")
            return True
        if blocker_id not in dm_blocks:
            dm_blocks[blocker_id] = set()
        dm_blocks[blocker_id].add(target_id)
        await send_system(websocket, f"User {target_id} blocked. Their DMs will be silently dropped.")
        return True

    if cmd == "/unblock":
        if not args:
            await send_system(websocket, "Usage: /unblock <user_id>")
            return True
        blocker_id = get_user_id(websocket)
        target_id = args[0]
        if blocker_id in dm_blocks and target_id in dm_blocks[blocker_id]:
            dm_blocks[blocker_id].remove(target_id)
            await send_system(websocket, f"User {target_id} unblocked.")
        else:
            await send_system(websocket, "That user is not blocked.")
        return True

    if cmd == "/dms":
        uid = get_user_id(websocket)
        lines = ""
        for pair in dm_approved:
            if uid in pair:
                other_id = (pair - {uid}).pop()
                other_ws = find_user_ws(other_id)
                status = "online" if other_ws else "offline"
                other_name = get_user_name(other_ws) if other_ws else other_id
                lines += f"  {other_id}: {other_name} ({status})\n"
        pending_out = [(t, m) for (s, t), m in dm_pending.items() if s == uid]
        pending_in = [(s, m) for (s, t), m in dm_pending.items() if t == uid]
        if pending_out:
            lines += "Pending (sent):\n"
            for tid, _ in pending_out:
                tw = find_user_ws(tid)
                tname = get_user_name(tw) if tw else tid
                lines += f"  {tid}: {tname} (waiting)\n"
        if pending_in:
            lines += "Pending (received):\n"
            for sid, _ in pending_in:
                sw = find_user_ws(sid)
                sname = get_user_name(sw) if sw else sid
                lines += f"  {sid}: {sname} (/accept or /decline)\n"
        blocked = dm_blocks.get(uid, set())
        if blocked:
            lines += f"Blocked: {', '.join(blocked)}\n"
        if not lines:
            await send_system(websocket, "No DM conversations.")
        else:
            await send_system(websocket, "Your DMs:")
            await send_system(websocket, lines)
        return True

    if cmd == "/nick":
        if not args:
            await send_system(websocket, "Usage: /nick <new_name>")
            return True
        new_name = args[0]
        uid = get_user_id(websocket)
        if not is_valid_nickname(new_name):
            await send_system(websocket, "Nickname invalid. Use letters, numbers, _ or - (max 32 chars).")
            return True
        async with connection_lock:
            if new_name in get_taken_names():
                await send_system(websocket, f"Nickname '{new_name}' is already taken.")
                return True
        if uid in pending_nick_change and pending_nick_change[uid] == new_name:
            old_name = get_user_name(websocket)
            USER_INFO[websocket]["name"] = new_name
            pending_nick_change.pop(uid, None)
            await send_to_all(f"[SYSTEM] {old_name} is now known as {new_name}.")
        else:
            pending_nick_change[uid] = new_name
            await send_system(websocket, f"Change nickname to '{new_name}'? Type /nick {new_name} again to confirm.")
        return True

    if cmd == "/clear":
        if not user_is_admin:
            return False
        CHAT_HISTORY.clear()
        save_server_data()
        await send_to_all("[SYSTEM] Chat history has been cleared by an admin.")
        return True

    return False

def get_taken_names():
    return {info["name"] for info in USER_INFO.values()}

async def handle_chat(websocket):
    user_id = (await websocket.recv()).strip()

    if not user_id or len(user_id) != 12:
        await websocket.close()
        return

    if user_id in BANNED_IDS:
        await send_system(websocket, "You are banned from this chat.")
        await websocket.close()
        return

    while True:
        await send_system(websocket, "Enter your nickname: ")
        name_msg = await websocket.recv()
        name = name_msg.strip()

        if not is_valid_nickname(name):
            await send_system(websocket, "Nickname invalid. Use letters, numbers, _ or - (max 32 chars).")
            continue

        async with connection_lock:
            taken_names = get_taken_names()
            if name in taken_names:
                await send_system(websocket, f"Nickname '{name}' is already taken. Try again.")
                continue
            CLIENTS[websocket] = True
            USER_INFO[websocket] = {"user_id": user_id, "name": name}
            break

    if not ADMIN_IDS:
        ADMIN_IDS.add(user_id)
        await send_system(websocket, "You are the first user and have been made admin.")

    await send_system(websocket, f"Connected as {name} (ID: {user_id})")
    if SERVER_MOTD:
        await send_system(websocket, f"MOTD: {SERVER_MOTD}")
    await send_system(websocket, "Type /help for commands")

    try:
        if CHAT_HISTORY:
            await websocket.send("-- Chat History --")
            for msg in CHAT_HISTORY[-MAX_HISTORY:]:
                await websocket.send(msg)
            await websocket.send("------------------")

        await send_to_all(f"[SYSTEM] {name} has joined the chat.")

        async for message in websocket:
            if not message.strip():
                continue

            if len(message) > MAX_MESSAGE_LENGTH:
                await send_system(websocket, f"Message too long (max {MAX_MESSAGE_LENGTH} chars).")
                continue

            if message.startswith("/"):
                handled = await handle_command(websocket, message)
                if handled:
                    continue

            if is_muted(user_id):
                remaining = int(MUTED_USERS[user_id] - time.time())
                await send_system(websocket, f"You are muted for {remaining} more seconds.")
                continue

            if not check_rate_limit(user_id):
                await send_system(websocket, "Slow down! You're sending messages too fast.")
                continue

            formatted_msg = f"[{timestamp()}] {name}: {message}"
            CHAT_HISTORY.append(formatted_msg)
            if len(CHAT_HISTORY) > MAX_HISTORY:
                CHAT_HISTORY.pop(0)

            await send_to_all(formatted_msg)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in USER_INFO:
            left_name = get_user_name(websocket)
            uid = get_user_id(websocket)
            CLIENTS.pop(websocket, None)
            USER_INFO.pop(websocket, None)
            user_message_times.pop(uid, None)
            stale_keys = [k for k in dm_pending if uid in k]
            for k in stale_keys:
                dm_pending.pop(k, None)
            stale_pairs = [p for p in dm_approved if uid in p]
            for p in stale_pairs:
                dm_approved.discard(p)
            dm_blocks.pop(uid, None)
            await send_to_all(f"[SYSTEM] {left_name} has left the chat.")

async def shutdown(server, room_id_dict):
    print("\nShutting down...")
    save_server_data()
    if CLIENTS:
        await send_to_all("[SYSTEM] Server is shutting down.")
        await asyncio.gather(
            *[ws.close() for ws in CLIENTS.keys()],
            return_exceptions=True
        )
    try:
        requests.post(
            url=GLOBSERVER + "/remove-server",
            json={"id": room_id_dict},
            timeout=5
        )
    except Exception:
        pass
    server.close()
    await server.wait_closed()
    print("Server stopped.")

def detect_globserver():
    for url in ["http://127.0.0.1:5000", "http://localhost:5000"]:
        try:
            r = requests.get(url + "/servers", timeout=2)
            if r.status_code == 200:
                return url, r.json()
        except Exception:
            continue
    return None, None

def connect_globserver(url):
    try:
        r = requests.get(url.rstrip("/") + "/servers", timeout=5)
        if r.status_code == 200:
            return url.rstrip("/"), r.json()
    except Exception:
        pass
    return None, None

async def main():
    server = await websockets.serve(handle_chat, "0.0.0.0", 55555)
    print("Starting Tunnel...")
    tunnel_result = try_cloudflare(55555)
    tunnel_url = tunnel_result.tunnel

    print(f"\n-- SERVER IS LIVE --")
    print(f"Connect via: {tunnel_url}")
    print(f"--------------------\n")

    glob_url, glob_data = detect_globserver()

    if not glob_url:
        print("No globserver found on localhost.")
        print("Enter your globserver URL (or press Enter to skip):")
        user_url = input("> ").strip()
        if user_url:
            if not user_url.startswith("http"):
                user_url = "https://" + user_url
            glob_url, glob_data = connect_globserver(user_url)
            if not glob_url:
                print(f"Could not connect to {user_url}. Running without registration.")
            else:
                print(f"Connected to globserver at {glob_url}")
        else:
            print("Running without globserver registration.")
    else:
        print(f"Globserver found at {glob_url}")

    room_id_dict = None
    if glob_url:
        global GLOBSERVER
        GLOBSERVER = glob_url
        server_count = glob_data.get("count", 0) if glob_data else 0

        if server_count == 0:
            room_id_dict = {"year": 2026, "region": "AN", "number": 0}
            print("No servers registered. Auto-registering as 2026-AN-0000...")
        else:
            print(f"{server_count} server(s) already registered.")
            number = random.randint(1000, 9999)
            while True:
                region = input("enter ISO region code (2 uppercase letters): ").strip().upper()
                if re.match(r'^[A-Z]{2}$', region):
                    break
                print("Invalid region code. Must be exactly 2 uppercase letters (e.g. US, PK, GB).")
            room_id_dict = {"year": date.today().year, "region": region, "number": number}

        response = requests.post(
            url=GLOBSERVER + "/add-server",
            json={"id": room_id_dict, "tunnel": str(tunnel_url).replace("https", "wss")}
        )
        code = f"{room_id_dict['year']}-{room_id_dict['region']}-{room_id_dict['number']:04d}"
        print(f"Room code: {code}")
        if response.status_code != 200:
            print("Warning: couldnt register with globserver")

    stop = asyncio.get_running_loop().create_future()

    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(
            sig, lambda: stop.set_result(None)
        )

    await stop
    if glob_url:
        await shutdown(server, room_id_dict)
    else:
        print("\nShutting down...")
        save_server_data()
        if CLIENTS:
            await send_to_all("[SYSTEM] Server is shutting down.")
            await asyncio.gather(
                *[ws.close() for ws in CLIENTS.keys()],
                return_exceptions=True
            )
        server.close()
        await server.wait_closed()
        print("Server stopped.")

if __name__ == "__main__":
    asyncio.run(main())
