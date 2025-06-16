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
ALLOWED_NUMBERS = os.getenv("ALLOWED_NUMBERS", "").split(",")

# Safe-load mapping for target names or IDs
try:
    NUMBER_MAP = json.loads(os.getenv("NUMBER_MAP", "{}"))
except Exception as e:
    print(f"❌ Invalid NUMBER_MAP: {e}")
    NUMBER_MAP = {}

# Flask app
app = Flask(__name__)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
discord_ready = asyncio.Event()

# Function to send SMS by calling SMSSync API (Android phone SMS sending)
def send_sms_via_smssync(to_number, message):
    # SMSSync doesn't provide an official API, but some forks do HTTP GET to send SMS
    # Replace this URL with your Android device's SMSSync endpoint and parameters
    smssync_url = os.getenv("SMSSYNC_SEND_URL")  # e.g. "http://android_phone_ip:port/send_sms"
    if not smssync_url:
        print("❌ SMSSync send URL not set in environment variables.")
        return
    payload = {
        "phone": to_number,
        "message": message
    }
    try:
        r = requests.get(smssync_url, params=payload, timeout=10)
        if r.status_code == 200:
            print(f"📤 SMS sent via SMSSync to {to_number}: {message}")
        else:
            print(f"❌ SMSSync send failed {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Exception sending SMS via SMSSync: {e}")

# Discord events
@client.event
async def on_ready():
    print(f"✅ Discord bot logged in as {client.user}")
    discord_ready.set()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    # Compose SMS content to send
    if isinstance(message.channel, discord.DMChannel):
        content = f"[DM] {message.author.name}: {message.content}"
    else:
        content = f"[#{message.channel.name}] {message.author.name}: {message.content}"

    # Send SMS to the target phone number (your Nokia)
    target_number = os.getenv("TARGET_PHONE_NUMBER")
    if target_number:
        # Send SMS in a background thread to not block the event loop
        def send_sms_thread():
            send_sms_via_smssync(target_number, content)
        Thread(target=send_sms_thread).start()
    else:
        print("❌ TARGET_PHONE_NUMBER not set in environment variables.")

# Send message to Discord from SMS content
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

        print(f"❌ Could not find a suitable channel or user: {resolved}")

    except Exception as e:
        print(f"❌ Error sending to Discord: {e}")

# Flask route for incoming SMS from SMSSync (uses 'sender' and 'message')
@app.route("/incoming", methods=["POST"])

def incoming():
    print("Headers:", request.headers)
    print("Body:", request.form)
    print("SMS received:", request.form)

    return receive_sms()


def receive_sms():
    data = request.form
    from_number = data.get("from")
    content = data.get("message")

    if not from_number or not content:
        return ("Missing required fields", 400)

    if from_number not in ALLOWED_NUMBERS:
        return ("Forbidden", 403)

    if " " not in content:
        return ("Invalid format. Use: target message", 400)

    target, msg = content.split(" ", 1)
    target = target.lstrip("@")
    resolved = NUMBER_MAP.get(target, target)

    asyncio.run_coroutine_threadsafe(send_to_discord(resolved, msg), client.loop)

    return ("Message accepted", 200)

# Start Flask in thread
def start_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    Thread(target=start_flask).start()
    client.run(BOT_TOKEN)
