import os
import json
import discord
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import asyncio
from threading import Thread

# Setup event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_NUMBERS = os.getenv("ALLOWED_NUMBERS", "").split(",")

# Optional: Map user-friendly keys to Discord IDs
try:
    NUMBER_MAP = json.loads(os.getenv("NUMBER_MAP", "{}"))
except Exception as e:
    print(f"❌ Invalid NUMBER_MAP: {e}")
    NUMBER_MAP = {}

# Flask app
app = Flask(__name__)

# Discord client setup
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
discord_ready = asyncio.Event()

# Discord bot events
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
    print(f"📤 Would send SMS: {content}")  # Sending is optional now

# Separated Discord sender function
async def send_to_discord(resolved, msg):
    await discord_ready.wait()
    try:
        if resolved.isdigit():
            channel = client.get_channel(int(resolved))
            if channel:
                await channel.send(msg)
                print(f"📤 Sent to channel #{channel.name} (ID: {resolved})", flush=True)
                return

            user = await client.fetch_user(int(resolved))
            await user.send(msg)
            print(f"📤 Sent DM to user {user.name} (ID: {resolved})", flush=True)
            return
        else:
            for guild in client.guilds:
                channel = discord.utils.get(guild.channels, name=resolved)
                if channel:
                    await channel.send(msg)
                    print(f"📤 Sent to channel #{channel.name} (by name)", flush=True)
                    return

        print(f"❌ Could not find a suitable channel or user: {resolved}", flush=True)

    except Exception as e:
        print(f"❌ Error sending to Discord: {e}", flush=True)

# Incoming webhook (Android app calls this)
@app.route("/incoming", methods=["POST"])
def receive_sms():
    try:
        data = request.get_json()
        from_number = data.get("from")
        content = data.get("message")

        if not from_number or not content:
            return jsonify({"error": "Missing fields"}), 400

        if from_number not in ALLOWED_NUMBERS:
            return jsonify({"error": "Forbidden"}), 403

        if " " not in content:
            return jsonify({"error": "Invalid format. Use: target message"}), 400

        target, msg = content.split(" ", 1)
        target = target.lstrip("@")
        resolved = NUMBER_MAP.get(target, target)

        asyncio.run_coroutine_threadsafe(send_to_discord(resolved, msg), client.loop)
        return jsonify({"status": "Message accepted"}), 200

    except Exception as e:
        print(f"❌ Error in /incoming: {e}")
        return jsonify({"error": str(e)}), 500

# Start Flask in a thread
def start_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# Start Discord bot
def start_discord():
    try:
        print("🟡 Starting Discord bot...")
        loop.run_until_complete(client.start(BOT_TOKEN))
    except Exception as e:
        print(f"❌ Discord bot failed to start: {e}")

# Launch
if __name__ == "__main__":
    Thread(target=start_flask).start()
    client.run(BOT_TOKEN)
