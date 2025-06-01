import os
import json
import discord
import requests
from flask import Flask, request
from dotenv import load_dotenv
import asyncio
from threading import Thread
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Load env vars
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELERIVET_API_KEY = os.getenv("TELERIVET_API_KEY")
TELERIVET_PROJECT_ID = os.getenv("TELERIVET_PROJECT_ID")
TELERIVET_PHONE_ID = os.getenv("TELERIVET_PHONE_ID")
TARGET_PHONE_NUMBER = os.getenv("TARGET_PHONE_NUMBER")
ALLOWED_NUMBERS = os.getenv("ALLOWED_NUMBERS", "").split(",")

# Safe-load mapping
try:
    NUMBER_MAP = json.loads(os.getenv("NUMBER_MAP", "{}"))
except Exception as e:
    print(f"❌ Invalid NUMBER_MAP: {e}")
    NUMBER_MAP = {}

# Flask app
app = Flask(__name__)

# Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
discord_ready = asyncio.Event()

# Send SMS
def send_sms(message):
    url = f"https://api.telerivet.com/v1/projects/{TELERIVET_PROJECT_ID}/messages/send"
    payload = {
        "phone_id": TELERIVET_PHONE_ID,
        "to_number": TARGET_PHONE_NUMBER,
        "content": message
    }
    response = requests.post(url, auth=(TELERIVET_API_KEY, ""), json=payload)
    if response.status_code != 200:
        print(f"❌ Failed to send SMS: {response.status_code} - {response.text}")
    else:
        print(f"📤 SMS sent: {message}")

# Discord events
@client.event
async def on_ready():
    print(f"✅ Discord bot logged in as {client.user}")
    discord_ready.set()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        content = f"[DM] {message.author.name}: {message.content}"
    else:
        content = f"[#{message.channel.name}] {message.author.name}: {message.content}"
    send_sms(content)

# Flask route
@app.route("/incoming", methods=["POST"])
def receive_sms():
    data = request.form
    from_number = data.get("from_number")
    content = data.get("content")

    if from_number not in ALLOWED_NUMBERS:
        return "Forbidden", 403

    if not content or " " not in content:
        return "Invalid format. Use: target message", 400

    target, msg = content.split(" ", 1)
    target = target.lstrip("@")
    resolved = NUMBER_MAP.get(target, target)

    async def send():
        await discord_ready.wait()
        try:
            if resolved.isdigit():
                obj = client.get_channel(int(resolved))
                if obj:
                    await obj.send(msg)
                    print(f"📤 Sent to channel {resolved}")
                    return
                user = await client.fetch_user(int(resolved))
                await user.send(msg)
                print(f"📤 Sent DM to user {resolved}")
                return
            else:
                for user in client.users:
                    if user.name.lower() == resolved.lower():
                        await user.send(msg)
                        print(f"📤 Sent DM to user {user.name}")
                        return
                print(f"❌ No user found: {resolved}")
        except Exception as e:
            print(f"❌ Error sending message: {e}")

    asyncio.run_coroutine_threadsafe(send(), client.loop)
    return "Message accepted", 200

# Start Flask in thread
def start_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def start_discord():
    try:
        print("🟡 Starting Discord bot...")
        loop.run_until_complete(client.start(BOT_TOKEN))
    except Exception as e:
        print(f"❌ Discord bot failed to start: {e}")

# Start everything
if __name__ == "__main__":
    Thread(target=start_flask).start()
    client.run(BOT_TOKEN)
