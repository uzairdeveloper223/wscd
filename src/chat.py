import asyncio
import websockets
import machine
import signal

MAX_RETRIES = 3
RETRY_DELAY = 3

async def _session(uri):
    async with websockets.connect(uri) as ws:
        print(f"--- Connected ---")

        await ws.send(machine.get_id())

        ban_check = await ws.recv()
        if ban_check.startswith("[SYSTEM] You are banned"):
            print(ban_check)
            return False

        nickname_msg = ban_check
        print(nickname_msg, end="")
        name = input("")
        while not name.strip():
            print(nickname_msg, end="")
            name = input("")
        await ws.send(name)

        result_msg = await ws.recv()

        while result_msg.startswith("[SYSTEM] Nickname"):
            print(result_msg)
            print(nickname_msg, end="")
            name = input("")
            while not name.strip():
                print(nickname_msg, end="")
                name = input("")
            await ws.send(name)
            result_msg = await ws.recv()

        while result_msg.startswith("[SYSTEM]"):
            print(result_msg)
            if "Type /help" in result_msg:
                break
            result_msg = await ws.recv()

        async def receive():
            try:
                async for message in ws:
                    if "[DM from" in message or "[DM to" in message:
                        print(f"\r\033[K\033[36m{message}\033[0m", flush=True)
                    elif message.startswith("[SYSTEM]") or message.startswith("--"):
                        print(f"\r\033[K\033[90m{message}\033[0m", flush=True)
                    else:
                        print(f"\r\033[K{message}\n{name} > ", end="", flush=True)
            except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                pass

        async def send():
            loop = asyncio.get_running_loop()
            try:
                while True:
                    msg = await loop.run_in_executor(None, input, f"{name} > ")
                    if msg.strip():
                        await ws.send(msg)
            except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError, EOFError):
                pass

        receive_task = asyncio.create_task(receive())
        send_task = asyncio.create_task(send())

        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(
                sig, lambda: [t.cancel() for t in [receive_task, send_task]]
            )

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

    return True

async def chat(tunnel_dict):
    uri = tunnel_dict.get('link', '')

    if not uri or not uri.startswith('wss://'):
        print("Could not find a valid tunnel URL.")
        return

    retries = 0
    while retries <= MAX_RETRIES:
        try:
            result = await _session(uri)
            if not result:
                return
            break
        except (asyncio.CancelledError, KeyboardInterrupt):
            break
        except websockets.exceptions.ConnectionClosed:
            retries += 1
            if retries <= MAX_RETRIES:
                print(f"\n--- Connection lost. Reconnecting ({retries}/{MAX_RETRIES})... ---")
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"\n--- Failed to reconnect after {MAX_RETRIES} attempts. ---")
        except Exception as e:
            retries += 1
            if retries <= MAX_RETRIES:
                print(f"\n[Error] {e}. Reconnecting ({retries}/{MAX_RETRIES})...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"\n--- Failed to reconnect after {MAX_RETRIES} attempts. ---")

    print("--- Session Ended, use Ctrl Z to exit ---")
