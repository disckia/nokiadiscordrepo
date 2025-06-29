import os
import json
import discord
import requests
import uuid
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import asyncio
from threading import Thread
import time

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Load env vars
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_NUMBERS = os.getenv("ALLOWED_NUMBERS", "").split(",")
PROJECT_ID = os.getenv("TELERIVET_PROJECT_ID")
API_KEY = os.getenv("TELERIVET_API_KEY")
PHONE_ID = os.getenv("TELERIVET_PHONE_ID")

# Safe-load mapping for target names or IDs
try:
    NUMBER_MAP = json.loads(os.getenv("NUMBER_MAP", "{}"))
except Exception as e:
    print(f"❌ Invalid NUMBER_MAP: {e}")
    NUMBER_MAP = {}

# Target phone for SMS delivery
TARGET_PHONE_NUMBER = os.getenv("TARGET_PHONE_NUMBER")

# Flask app
app = Flask(__name__)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
discord_ready = asyncio.Event()

# Discord events
@client.event
async def on_ready():
    print(f"✅ Discord bot logged in as {client.user}")
    discord_ready.set()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Compose message
    if isinstance(message.channel, discord.DMChannel):
        content = f"[DM] {message.author.name}: {message.content}"
    else:
        content = f"[#{message.channel.name}] {message.author.name}: {message.content}"

    if TARGET_PHONE_NUMBER:
        print(f"📥 Sending SMS to {TARGET_PHONE_NUMBER}: {content}")
        send_sms_via_telerivet(TARGET_PHONE_NUMBER, content)
    else:
        print("❌ TARGET_PHONE_NUMBER not set.")

# Send SMS via Telerivet API with increased timeout and retries
def send_sms_via_telerivet(to_number, message):
    url = f"https://api.telerivet.com/v1/projects/{PROJECT_ID}/messages/send"
    payload = {
        "to": to_number,
        "content": message,
        "phone_id": PHONE_ID
    }

    headers = {
        'Content-Type': 'application/json'  # Corrected to application/json
    }

    max_retries = 3
    retry_delay = 5  # Seconds
    timeout = 30  # Increase timeout to 30 seconds

    for attempt in range(max_retries):
        try:
            response = requests.post(url, auth=(API_KEY, ""), json=payload, headers=headers, timeout=timeout)
            if response.status_code == 200:
                print("📤 SMS sent successfully!")
                return
            else:
                print(f"❌ Telerivet error {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout error on attempt {attempt + 1}. Retrying in {retry_delay} seconds...")
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")

        time.sleep(retry_delay)  # Wait before retrying

    print("❌ Failed to send SMS after retries.")

# Webhook to receive SMS from Telerivet (Telerivet service must post here)
@app.route("/incoming", methods=["POST"])
def incoming():
    try:
        # Log headers and raw data
        print("Request Headers:", request.headers)
        print("Raw Data:", request.data)

        # Force parsing JSON or fallback to form data if JSON is not available
        data = request.get_json(force=True) or request.form.to_dict()

        if not data:
            print("❌ No data received or malformed request")
            return "Invalid content", 415

        print("📩 Incoming SMS data:", data)

        from_number = data.get("from_number") or data.get("from")
        content = data.get("content") or data.get("message")

        if not content or " " not in content:
            print(f"❌ Invalid format or missing content: {content}")
            return ("Invalid format. Use: target message", 400)

        target, msg = content.split(" ", 1)
        target = target.lstrip("@")
        resolved = NUMBER_MAP.get(target, target)

        print(f"📤 Resolving target: {resolved} => {msg}")
        asyncio.run_coroutine_threadsafe(send_to_discord(resolved, msg), client.loop)

        return ("Message accepted", 200)

    except KeyError as e:
        print(f"❌ Missing expected key in incoming data: {e}")
        return "Bad request", 400
    except Exception as e:
        print(f"❌ Error processing incoming data: {e}")
        return "Internal server error", 500

# Send message to Discord from SMS
async def send_to_discord(resolved, msg):
    await discord_ready.wait()
    try:
        if resolved.isdigit():
            channel = client.get_channel(int(resolved))
            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(msg)
                print(f"📤 Sent to channel #{channel.name} (ID: {resolved})")
                return

            user = await client.fetch_user(int(resolved))
            await user.send(msg)
            print(f"📤 Sent DM to user {user.name} (ID: {resolved})")
            return
        else:
            for guild in client.guilds:
                channel = discord.utils.get(guild.channels, name=resolved)
                if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                    await channel.send(msg)
                    print(f"📤 Sent to channel #{channel.name} (by name)")
                    return

        print(f"❌ Could not find channel or user: {resolved}")

    except Exception as e:
        print(f"❌ Error sending to Discord: {e}")

# Start Flask in thread
def start_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

if __name__ == "__main__":
    Thread(target=start_flask).start()
    client.run(BOT_TOKEN)
