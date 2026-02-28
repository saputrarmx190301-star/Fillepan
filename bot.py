import asyncio
import os
import sqlite3
import uuid
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand
)
from pyrogram.errors import FloodWait, UserNotParticipant

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

FORCE_CHANNEL = int(os.getenv("FORCE_CHANNEL"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
STORAGE_CHANNEL = int(os.getenv("STORAGE_CHANNEL"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= DATABASE =================
db = sqlite3.connect("database.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS files (code TEXT, file_id TEXT, size INTEGER)")
db.commit()

# ================= SET COMMAND MENU =================
@app.on_message(filters.command("setcmd") & filters.user(ADMIN_ID))
async def set_commands(client, message):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("upload", "Upload file"),
        BotCommand("create", "Create link"),
        BotCommand("account", "Account info"),
        BotCommand("broadcast", "Broadcast (Admin)")
    ]
    await app.set_bot_commands(commands)
    await message.reply("✅ Command menu updated.")

# ================= FORCE JOIN =================
async def check_join(user_id):
    try:
        member = await app.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except:
        return False

# ================= MAIN MENU =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload File", callback_data="upload")],
        [InlineKeyboardButton("📊 Statistik", callback_data="stats")],
        [InlineKeyboardButton("📢 Channel Bot", url=CHANNEL_LINK)]
    ])

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    db.commit()

    if not await check_join(user_id):
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)]]
        )
        return await message.reply(
            "🔒 Silakan join channel terlebih dahulu.",
            reply_markup=btn
        )

    args = message.text.split()
    if len(args) > 1:
        return await send_files(user_id, args[1])

    await message.reply(
        "👋 Welcome to Premium File Bot",
        reply_markup=main_menu()
    )

# ================= UPLOAD SYSTEM =================
user_sessions = {}

@app.on_callback_query(filters.regex("upload"))
async def upload_button(client, callback_query):
    user_sessions[callback_query.from_user.id] = {
        "files": [],
        "progress": None
    }
    await callback_query.message.edit("📤 Kirim video / file sekarang.")
    await callback_query.answer()

@app.on_message(filters.video | filters.document)
async def handle_media(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return

    session = user_sessions[user_id]
    forwarded = await message.forward(STORAGE_CHANNEL)

    if message.video:
        size = message.video.file_size
        file_id = forwarded.video.file_id
    else:
        size = message.document.file_size
        file_id = forwarded.document.file_id

    session["files"].append((file_id, size))

    total_files = len(session["files"])
    total_size = sum(x[1] for x in session["files"])

    text = (
        f"📦 File: {total_files}\n"
        f"💾 Size: {round(total_size/1024/1024,2)} MB\n\n"
        "Klik Create untuk membuat link."
    )

    if session["progress"]:
        await session["progress"].edit(text)
    else:
        msg = await message.reply(text)
        session["progress"] = msg

# ================= CREATE =================
@app.on_message(filters.command("create"))
async def create(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions or not user_sessions[user_id]["files"]:
        return await message.reply("❌ Tidak ada file.")

    code = str(uuid.uuid4())[:8]

    for file_id, size in user_sessions[user_id]["files"]:
        cursor.execute("INSERT INTO files VALUES (?, ?, ?)", (code, file_id, size))
    db.commit()

    bot_username = (await app.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.reply(
        f"🎉 Pack Created!\n\n🔗 {link}\n\n🔑 `{code}`",
        disable_web_page_preview=True
    )

    if user_sessions[user_id]["progress"]:
        await user_sessions[user_id]["progress"].delete()

    del user_sessions[user_id]

# ================= SEND FILES + PAGINATION =================
async def send_files(user_id, code, page=1):
    cursor.execute("SELECT file_id FROM files WHERE code=?", (code,))
    results = cursor.fetchall()
    if not results:
        return

    files = [x[0] for x in results]
    per_page = 10
    total_pages = (len(files) + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page

    for file_id in files[start:end]:
        try:
            await app.send_cached_media(user_id, file_id)
            await asyncio.sleep(0.4)
        except FloodWait as e:
            await asyncio.sleep(e.value)

    if total_pages <= 1:
        return

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅", callback_data=f"{code}|{page-1}"))

    for p in range(1, total_pages + 1):
        buttons.append(
            InlineKeyboardButton(
                f"[{p}]" if p == page else str(p),
                callback_data="ignore" if p == page else f"{code}|{p}"
            )
        )

    if page < total_pages:
        buttons.append(InlineKeyboardButton("➡", callback_data=f"{code}|{page+1}"))

    await app.send_message(
        user_id,
        "📂 Pilih halaman:",
        reply_markup=InlineKeyboardMarkup([buttons])
    )

# ================= CALLBACK =================
@app.on_callback_query()
async def callback(client, callback_query):
    data = callback_query.data
    if data == "ignore":
        return await callback_query.answer()
    if "|" in data:
        code, page = data.split("|")
        await send_files(callback_query.from_user.id, code, int(page))
        return await callback_query.answer()

    if data == "stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT code) FROM files")
        packs = cursor.fetchone()[0]
        await callback_query.message.edit(
            f"📊 Statistik\n\n👥 Users: {users}\n📦 Packs: {packs}",
            reply_markup=main_menu()
        )
        await callback_query.answer()

# ================= DETECT CODE =================
@app.on_message(filters.text & ~filters.command(["start","create","setcmd","broadcast"]))
async def detect_code(client, message):
    await send_files(message.from_user.id, message.text.strip())

# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Reply pesan untuk broadcast.")

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    sent = 0
    for user in users:
        try:
            await message.reply_to_message.copy(user[0])
            await asyncio.sleep(0.05)
            sent += 1
        except:
            pass

    await message.reply(f"✅ Broadcast selesai.\nTerkirim: {sent}")

# ================= RUN =================
app.run()
