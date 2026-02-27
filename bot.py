import asyncio
import random
import string
import asyncpg
from math import ceil
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import *

app = Client(
    "premium_storage_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

db = None

# ================= DATABASE =================

async def connect_db():
    global db
    db = await asyncpg.connect(DATABASE_URL)

async def create_tables():
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id BIGINT PRIMARY KEY
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS files(
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        file_id TEXT,
        size BIGINT
    );
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS packs(
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        code TEXT UNIQUE
    );
    """)

# ================= UTIL =================

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def format_size(size):
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def channel_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Bot", url=GROUP_LINK)]
    ])

# ================= START =================

@app.on_message(filters.private & filters.command("start"))
async def start(client, message):
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING",
        message.from_user.id
    )

    args = message.text.split()

    await message.reply(
        "✨ Welcome to Premium Storage Bot ✨\n\n"
        "📤 Kirim video/file untuk upload\n"
        "📦 Gunakan /getcode untuk buat pack\n"
        "📋 Kirim CODE langsung untuk buka pack\n",
        reply_markup=channel_button()
    )

    if len(args) > 1:
        await send_pack(message, args[1], 1)

# ================= ANIMASI UPLOAD =================

async def upload_animation(msg):
    frames = [
        "⬜⬜⬜⬜⬜ 0%",
        "🟩⬜⬜⬜⬜ 20%",
        "🟩🟩⬜⬜⬜ 40%",
        "🟩🟩🟩⬜⬜ 60%",
        "🟩🟩🟩🟩⬜ 80%",
        "🟩🟩🟩🟩🟩 100%"
    ]

    for f in frames:
        await msg.edit(f"📤 Uploading...\n\n{f}")
        await asyncio.sleep(0.4)

# ================= HANDLE FILE =================

@app.on_message(filters.private & (filters.video | filters.document))
async def upload_file(client, message):
    user_id = message.from_user.id

    status = await message.reply("📤 Preparing upload...")
    await upload_animation(status)

    forwarded = await message.forward(STORAGE_CHANNEL)

    if forwarded.video:
        file_id = forwarded.video.file_id
        size = forwarded.video.file_size
    else:
        file_id = forwarded.document.file_id
        size = forwarded.document.file_size

    await db.execute(
        "INSERT INTO files(user_id,file_id,size) VALUES($1,$2,$3)",
        user_id, file_id, size
    )

    total_files = await db.fetchval(
        "SELECT COUNT(*) FROM files WHERE user_id=$1",
        user_id
    )

    total_size = await db.fetchval(
        "SELECT SUM(size) FROM files WHERE user_id=$1",
        user_id
    )

    await status.edit(
        f"✅ Upload Complete!\n\n"
        f"📦 Total File: {total_files}\n"
        f"💾 Total Size: {format_size(total_size)}",
        reply_markup=channel_button()
    )

# ================= GETCODE =================

@app.on_message(filters.private & filters.command("getcode"))
async def getcode(client, message):
    user_id = message.from_user.id

    files = await db.fetch(
        "SELECT * FROM files WHERE user_id=$1",
        user_id
    )

    if not files:
        return await message.reply("❌ Tidak ada file.")

    total_size = sum(f["size"] for f in files)
    code = generate_code()

    await db.execute(
        "INSERT INTO packs(user_id,code) VALUES($1,$2)",
        user_id, code
    )

    bot_username = (await app.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.reply(
        f"🎉 Pack Created!\n\n"
        f"📦 Total File: {len(files)}\n"
        f"💾 Total Size: {format_size(total_size)}\n\n"
        f"🔗 Link:\n{link}\n\n"
        f"🔑 Code:\n{code}",
        reply_markup=channel_button()
    )

# ================= CODE DIRECT =================

@app.on_message(filters.private & filters.text)
async def code_direct(client, message):
    code = message.text.strip().upper()

    pack = await db.fetchrow("SELECT * FROM packs WHERE code=$1", code)
    if pack:
        await send_pack(message, code, 1)

# ================= SEND PACK PREMIUM =================

async def send_pack(message, code, page):
    user_id = message.from_user.id

    pack = await db.fetchrow("SELECT * FROM packs WHERE code=$1", code)
    if not pack:
        return await message.reply("❌ Code tidak ditemukan.")

    files = await db.fetch(
        "SELECT file_id,size FROM files WHERE user_id=$1",
        pack["user_id"]
    )

    if not files:
        return await message.reply("❌ Tidak ada file.")

    per_page = 10
    total_pages = ceil(len(files) / per_page)

    start = (page - 1) * per_page
    end = start + per_page

    for f in files[start:end]:
        await app.send_video(user_id, f["file_id"])

    buttons = []

    if page > 1:
        buttons.append(
            InlineKeyboardButton("⬅ Prev", callback_data=f"page_{code}_{page-1}")
        )

    buttons.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop")
    )

    if page < total_pages:
        buttons.append(
            InlineKeyboardButton("Next ➡", callback_data=f"page_{code}_{page+1}")
        )

    keyboard = [
        buttons,
        [InlineKeyboardButton("📢 Channel Bot", url=GROUP_LINK)]
    ]

    await message.reply(
        f"📦 Page {page} of {total_pages}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= PAGINATION =================

@app.on_callback_query(filters.regex("^page_"))
async def pagination(client, cb):
    _, code, page = cb.data.split("_")
    await cb.message.delete()
    await send_pack(cb.message, code, int(page))

@app.on_callback_query(filters.regex("noop"))
async def noop(client, cb):
    await cb.answer()

# ================= RUN =================

async def main():
    await connect_db()
    await create_tables()
    await app.start()
    print("Premium Bot Running...")
    await idle()

asyncio.get_event_loop().run_until_complete(main())
