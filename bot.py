import asyncio
import os
import sqlite3
import uuid
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
    code TEXT,
    file_id TEXT,
    size INTEGER
)
""")

db.commit()

# ================= FORCE JOIN =================
async def check_join(user_id):
    try:
        member = await app.get_chat_member(FORCE_CHANNEL, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except UserNotParticipant:
        return False
    except:
        return False
    return False

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
            "🔒 Untuk menggunakan bot ini, silakan join channel terlebih dahulu.",
            reply_markup=btn
        )

    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        return await send_files(user_id, code)

    await message.reply(
        "👋 Selamat datang di File Share Bot\n\n"
        "📤 /upload - Upload file/video\n"
        "📦 /mycode - Info code\n"
        "👤 /account - Info akun\n"
        "📢 /Channelbot - Channel bot"
    )

# ================= UPLOAD SYSTEM =================
user_sessions = {}

@app.on_message(filters.command("upload"))
async def upload(client, message):
    user_sessions[message.from_user.id] = {
        "files": [],
        "progress": None
    }
    await message.reply("📤 Kirim video / file sekarang.")

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
        f"📦 File Uploaded: {total_files}\n"
        f"💾 Total Size: {round(total_size/1024/1024,2)} MB\n\n"
        "Ketik /create untuk membuat link."
    )

    if session["progress"]:
        await session["progress"].edit(text)
    else:
        msg = await message.reply(text)
        session["progress"] = msg

# ================= CREATE PACK =================
@app.on_message(filters.command("create"))
async def create(client, message):
    user_id = message.from_user.id

    if user_id not in user_sessions or not user_sessions[user_id]["files"]:
        return await message.reply("❌ Tidak ada file untuk dibuat.")

    code = str(uuid.uuid4())[:8]

    for file_id, size in user_sessions[user_id]["files"]:
        cursor.execute("INSERT INTO files VALUES (?, ?, ?)", (code, file_id, size))

    db.commit()

    bot_username = (await app.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.reply(
        f"🎉 Pack Berhasil Dibuat!\n\n"
        f"🔗 Link:\n{link}\n\n"
        f"🔑 Code:\n`{code}`",
        disable_web_page_preview=True
    )

    if user_sessions[user_id]["progress"]:
        await user_sessions[user_id]["progress"].delete()

    del user_sessions[user_id]

# ================= DETECT CODE =================
@app.on_message(filters.text & ~filters.command(["start","upload","create"]))
async def detect_code(client, message):
    code = message.text.strip()
    await send_files(message.from_user.id, code)

# ================= SEND FILES (SHOWFILES STYLE PAGINATION) =================
async def send_files(user_id, code, page=1):
    cursor.execute("SELECT file_id FROM files WHERE code=?", (code,))
    results = cursor.fetchall()
    if not results:
        return

    files = [x[0] for x in results]

    per_page = 10
    total = len(files)
    total_pages = (total + per_page - 1) // per_page

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
        buttons.append(
            InlineKeyboardButton("⬅ Prev", callback_data=f"{code}|{page-1}")
        )

    for p in range(1, total_pages + 1):
        if p == page:
            buttons.append(
                InlineKeyboardButton(f"•{p}•", callback_data="ignore")
            )
        else:
            buttons.append(
                InlineKeyboardButton(str(p), callback_data=f"{code}|{p}")
            )

    if page < total_pages:
        buttons.append(
            InlineKeyboardButton("Next ➡", callback_data=f"{code}|{page+1}")
        )

    buttons.append(
        InlineKeyboardButton("📢 Channel Bot", url=CHANNEL_LINK)
    )

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

    code, page = data.split("|")
    await send_files(callback_query.from_user.id, code, int(page))
    await callback_query.answer()

# ================= EXTRA COMMANDS =================
@app.on_message(filters.command("mycode"))
async def mycode(client, message):
    await message.reply("📦 Code tersimpan permanen.")

@app.on_message(filters.command("account"))
async def account(client, message):
    await message.reply(f"👤 ID Anda: {message.from_user.id}")

@app.on_message(filters.command("Channelbot"))
async def channelbot(client, message):
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📢 Channel Bot", url=CHANNEL_LINK)]]
    )
    await message.reply("Klik tombol di bawah:", reply_markup=btn)

# ================= RUN =================
app.run()
