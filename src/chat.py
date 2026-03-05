import asyncio
import re
import websockets

async def chat(tunnel_dict):
    link_str = tunnel_dict.get('link', '')
    match = re.search(r"tunnel='(wss://[^']+)'", link_str)
    
    if not match:
        print("Could not find a valid tunnel URL.")
        return
        
    uri = match.group(1)
    name = input("Enter your nickname: ")

    try:
        async with websockets.connect(uri) as ws:
            print(f"--- Connected ---")

            async def receive():
                try:
                    async for message in ws:
                        print(f"\r{message}\n! {name} ! >>>>>> ", end="", flush=True)
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    pass

            async def send():
                loop = asyncio.get_running_loop()
                try:
                    while True:
                        msg = await loop.run_in_executor(None, input, f"! {name} ! >>>>>> ")
                        await ws.send(f"{name} >> {msg}\n")
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    pass

            receive_task = asyncio.create_task(receive())
            send_task = asyncio.create_task(send())

            done, pending = await asyncio.wait(
                [receive_task, send_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        print(f"\n[Error] {e}")
    finally:
        print("\n--- Session Ended ---")
