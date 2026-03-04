import asyncio
import websockets
import locale
import random
from datetime import date
from pycloudflared import try_cloudflare
import requests
global GLOBSERVER
GLOBSERVER = "http://127.0.0.1:5000"

CLIENTS = set()

async def handle_chat(websocket):
    CLIENTS.add(websocket)
    print(websocket)
    try:
        async for message in websocket:
            if CLIENTS:
                await asyncio.gather(*[client.send(message) for client in CLIENTS])
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.remove(websocket)

async def main():
    async with websockets.serve(handle_chat, "0.0.0.0", 55555):
        print("Starting Tunnel...")
        tunnel_url = try_cloudflare(55555)
        
        
        print(f"\n--- SERVER IS LIVE ---")
        print(f"Connect via: {tunnel_url}")
        print(f"----------------------\n")
        number = random.randint(1000, 9999)
        region = input("enter ISO region code (2 letters (e.g US, AE, SA)): ")
        response = requests.post(url=GLOBSERVER + "/add-server", data={"id": {"year": date.today().year, "region": region, "numbers": number}, "tunnel": str(tunnel_url).replace("https", "wss")})
        print(f"code: {date.today().year}-{region}-{number}")
        if response != 200:
            print("couldnt register server")
            exit(1)

        
        await asyncio.Future()
if __name__ == "__main__":
    asyncio.run(main())
