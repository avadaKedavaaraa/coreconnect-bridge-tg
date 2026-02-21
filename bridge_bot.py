import os
import uuid
import logging
import html
import random
import threading
import http.server
import socketserver
from datetime import datetime
import pytz
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
from supabase import create_client, Client

# ==========================================
# ⚙️ CONFIGURATION & SETUP
# ==========================================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "").lower()

TARGET_SECTOR = "announcements" 
IST = pytz.timezone('Asia/Kolkata')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🌐 RENDER KEEP-ALIVE SERVER (SECURED)
# ==========================================
class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Only return a 200 OK status, NEVER serve files!
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"CoreConnect Bridge is Online and Secure.")
        
    def log_message(self, format, *args):
        pass # Suppress HTTP logs so your console stays clean

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
            print(f"📡 Secure Health server active on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Health Server Error: {e}")

threading.Thread(target=run_health_server, daemon=True).start()

# ==========================================
# 🧠 ETERNAL MEMORY (Supabase Persistence)
# ==========================================
CONFIG_ID = "BRIDGE_TOPIC_CONFIG"

def load_topic_id_from_db():
    try:
        res = supabase.table("items").select("content").eq("id", CONFIG_ID).execute()
        if res.data: return int(res.data[0]['content'])
    except Exception as e:
        logger.error(f"Memory Load Error: {e}")
    return None

def save_topic_id_to_db(topic_id):
    payload = {
        "id": CONFIG_ID,
        "title": "Bot Config",
        "content": str(topic_id),
        "type": "bot_metadata",
        "sector": "system",
        "date": datetime.now(IST).strftime("%Y.%m.%d %H:%M:%S")
    }
    try:
        supabase.table("items").upsert(payload).execute()
    except Exception as e:
        logger.error(f"Memory Save Error: {e}")

ACTIVE_TOPIC_ID = load_topic_id_from_db()

# ==========================================
# 🎭 MEME DATA
# ==========================================
NEON_GRADIENTS = [
    {"start": "#f43f5e", "end": "#e11d48", "name": "Cyber Rose"},
    {"start": "#38bdf8", "end": "#3b82f6", "name": "Electric Blue"},
    {"start": "#a855f7", "end": "#d946ef", "name": "Neon Amethyst"},
    {"start": "#fbbf24", "end": "#f59e0b", "name": "Warning Amber"}
]

MEME_RESPONSES = [
    "❌ **Abba nahi manenge!** (Permission Required)",
    "🤫 **Control, Majnu bhai, control!** Aap admin nahi hain.",
    "🤨 **Aap yahan naye aaye hain kya?** Entry restricted.",
    "🙅‍♂️ **Chhoti bachhi ho kya?** Access denied!",
    "🧐 **Yeh scheme sirf admins ke liye hai.**",
    "🚫 **Aap se na ho payega.**",
    "🚧 **Rukiye! Pehle admin baniye.**"
]

# ==========================================
# 🛡️ AUTHENTICATION & LOGIC
# ==========================================
async def is_sender_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user: return False
    if user.username and user.username.lower() == ADMIN_USER: return True
    if update.effective_chat.type != "private":
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except: return False
    return False

def get_ist_time() -> str:
    return datetime.now(IST).strftime("%Y.%m.%d %H:%M:%S")

async def verify_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_TOPIC_ID
    msg = update.message
    try: await msg.delete()
    except: pass

    if not await is_sender_authorized(update, context):
        try: await context.bot.send_message(chat_id=update.effective_user.id, text=random.choice(MEME_RESPONSES))
        except: pass
        return

    ACTIVE_TOPIC_ID = msg.message_thread_id
    save_topic_id_to_db(ACTIVE_TOPIC_ID)
    
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"🔗 **TOPIC LINKED!**\n━━━━━━━━━━━━\n✅ ID: `{ACTIVE_TOPIC_ID}`\n🧠 *Memory saved to Database.*",
            parse_mode=ParseMode.MARKDOWN
        )
    except: pass

async def auto_bridge_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_TOPIC_ID
    msg = update.message
    if not msg or not msg.text: return 

    is_private = update.effective_chat.type == "private"
    authorized = await is_sender_authorized(update, context)
    
    if not is_private:
        if ACTIVE_TOPIC_ID is not None and msg.message_thread_id != ACTIVE_TOPIC_ID:
            return 
    
    if not authorized:
        if msg.text.startswith("/") or is_private:
            await msg.reply_text(random.choice(MEME_RESPONSES), parse_mode=ParseMode.MARKDOWN)
        return

    try:
        lines = msg.text.split('\n')
        title = lines[0].strip() 
        raw_html = msg.text_html
        html_lines = raw_html.split('\n')
        content_html = '<br/>'.join(html_lines[1:]).strip() 
        if not content_html: content_html = "<i>Details in title.</i>"

        theme = random.choice(NEON_GRADIENTS)
        should_pin = any(x in title.upper() for x in ["⚠️", "🚨", "URGENT", "LAST DATE"])

        payload = {
            "id": str(uuid.uuid4()),
            "title": title, "content": content_html, "date": get_ist_time(),
            "type": "announcement", "sector": TARGET_SECTOR, "subject": "General announcements",
            "isUnread": True, "isPinned": should_pin, "author": f"{update.effective_user.first_name}",
            "style": { "titleColor": theme['start'], "titleColorEnd": theme['end'], "isGradient": True }
        }

        # Fix 2: Run the blocking Supabase call in a separate thread so it doesn't freeze the bot
        import asyncio
        await asyncio.to_thread(supabase.table("items").insert(payload).execute)
        
        # Fix 3: Isolate the DM receipt so a failed DM doesn't register as a DB failure
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=f"✅ **SYNCED TO WEB**\n━━━━━━━━━━━━\n📌 {html.escape(title)}\n📅 {get_ist_time()}",
                parse_mode=ParseMode.HTML
            )
        except Exception as dm_error:
            logger.warning(f"Could not send DM receipt to admin (they haven't started the bot): {dm_error}")
            
    except Exception as e:
        logger.error(f"Sync failed: {e}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_sender_authorized(update, context):
        await update.message.reply_text("🌉 **BRIDGE BOT ONLINE**\n*Receipts will be sent here.*")
    else:
        await update.message.reply_text(random.choice(MEME_RESPONSES))

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("verifytopic", verify_topic))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_bridge_listener))
    
    print(f"🥷 Stealth Bridge Active | Memory: {ACTIVE_TOPIC_ID is not None}")
    app.run_polling()

if __name__ == "__main__":
    main()