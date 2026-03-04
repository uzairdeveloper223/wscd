import asyncio
import websockets

async def chat(url):
    name = input("Enter your nickname: ")

    async with websockets.connect(url) as ws:
        print(f"Connected to room")

        
        async def receive():
            async for message in ws:
                print(f"\n{message}")
                

        async def send():
            while True:
                msg = await asyncio.get_event_loop().run_in_executor(None, input, f"! {name} ! >>>>>> ")
                await ws.send(f"{name} >> {msg}")

        await asyncio.gather(receive(), send())

if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        print("Exiting...")
