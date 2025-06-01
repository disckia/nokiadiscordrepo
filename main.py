# discord_sms_gateway.py
import discord
import os
import requests
from flask import Flask, request
import threading
from dotenv import load_dotenv
import asyncio
import json

load_dotenv()
# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELERIVET_API_KEY = os.getenv("TELERIVET_API_KEY")
TELERIVET_PROJECT_ID = os.getenv("TELERIVET_PROJECT_ID")
TELERIVET_PHONE_ID = os.getenv("TELERIVET_PHONE_ID")
TARGET_PHONE_NUMBER = os.getenv("TARGET_PHONE_NUMBER")  # Nokia number
ALLOWED_NUMBERS = os.getenv("ALLOWED_NUMBERS", "").split(",")  # Whitelist of numbers allowed to send SMS to Discord

# === Number to user/channel mapping from ENV ===
number_map_str = os.getenv("NUMBER_MAP", "{}")
try:
    NUMBER_MAP = json.loads(number_map_str)
except json.JSONDecodeError:
    print("❌ Failed to parse NUMBER_MAP from environment variable. Using empty dict.")
    NUMBER_MAP = {}

# === Setup Flask and Discord ===
app = Flask(__name__)
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
discord_ready = asyncio.Event()

# === Discord → SMS ===
def send_sms(message):
    url = f"https://api.telerivet.com/v1/projects/{TELERIVET_PROJECT_ID}/messages/send"
    payload = {
        "phone_id": TELERIVET_PHONE_ID,
        "to_number": TARGET_PHONE_NUMBER,
        "content": message
    }
    response = requests.post(url, auth=(TELERIVET_API_KEY, ""), json=payload)
    if response.status_code != 200:
        print(f"❌ SMS send failed: {response.status_code} - {response.text}")
    else:
        print(f"📤 SMS sent: {message}")

@client.event
async def on_ready():
    print(f"✅ Discord bot logged in as {client.user}")
    discord_ready.set()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        sms_msg = f"[DM] {message.channel.name}: {message.content}"
        print(f"📨 Forwarding Discord DM to SMS: {sms_msg}")
        send_sms(sms_msg)
    else:
        sms_msg = f"[Guild: {message.channel.name}] {message.author.name}: {message.content}"
        print(f"📨 Forwarding Guild message to SMS: {sms_msg}")
        send_sms(sms_msg)

# === SMS → Discord ===
@app.route("/incoming", methods=["POST"])
def receive_sms():
    try:
        data = request.form
        print("Received data:", data)
        from_number = data.get("from_number")
        content = data.get("content")

        if from_number not in ALLOWED_NUMBERS:
            print(f"Rejected from number: {from_number}")
            return "Number not allowed", 403

        if not content or " " not in content:
            print("Invalid content format")
            return "Invalid format. Use: target message", 400

        # Split on first space
        target, message = content.split(" ", 1)
        target = target.lstrip("@")  # Allow optional @ prefix

        # Load map from env and resolve target
        number_map = json.loads(os.getenv("NUMBER_MAP", "{}"))
        resolved = number_map.get(target, target)  # fall back to direct use

        async def send_discord():
            await discord_ready.wait()

            # If resolved is numeric → treat as ID
            if resolved.isdigit():
                try:
                    obj = client.get_channel(int(resolved))
                    if obj:
                        await obj.send(message)
                        print(f"📤 Sent to Channel ID {resolved}: {message}")
                        return
                    # If not a channel, maybe it's a user
                    user = await client.fetch_user(int(resolved))
                    await user.send(message)
                    print(f"📤 Sent DM to User ID {resolved}: {message}")
                    return
                except Exception as e:
                    print(f"❌ Failed to send to ID {resolved}: {e}")
                    return

            # If resolved is not an ID, match by username
            for user in client.users:
                if user.name.lower() == resolved.lower():
                    try:
                        await user.send(message)
                        print(f"📤 Sent DM to {user.name}: {message}")
                        return
                    except Exception as e:
                        print(f"❌ Failed to DM {user.name}: {e}")
                        return
            print(f"❌ User '{resolved}' not found")

        loop.create_task(send_discord())
        return "Message accepted", 200

    except Exception as e:
        import traceback
        print(f"Exception in /incoming: {e}")
        traceback.print_exc()
        return "Internal Server Error", 500

# === Threading ===
def start_flask():
    app.run(host='0.0.0.0', port=5000)

def start_discord():
    loop.run_until_complete(client.start(BOT_TOKEN))

if __name__ == "__main__":
    threading.Thread(target=start_flask).start()
    start_discord()
