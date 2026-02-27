import asyncio
import random
import string
import asyncpg
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import *

app = Client(
    "storage_bot",
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

async def is_joined(user_id):
    try:
        member = await app.get_chat_member(STORAGE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def join_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=CHANNEL_LINK)]
    ])

# ================= START =================

@app.on_message(filters.private & filters.command("start"))
async def start(client, message):
    await db.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT DO NOTHING",
        message.from_user.id
    )

    args = message.text.split()

    if len(args) > 1:
        await send_pack(message, args[1], 1)
    else:
        await message.reply("Kirim video untuk mulai upload.")

# ================= UPLOAD =================

@app.on_message(filters.private & (filters.video | filters.document))
async def upload(client, message):
    user_id = message.from_user.id

    try:
        forwarded = await message.forward(STORAGE_CHANNEL)

        if forwarded.video:
            file_id = forwarded.video.file_id
            size = forwarded.video.file_size
        elif forwarded.document:
            file_id = forwarded.document.file_id
            size = forwarded.document.file_size
        else:
            return await message.reply("File tidak valid.")

        await db.execute(
            "INSERT INTO files(user_id,file_id,size) VALUES($1,$2,$3)",
            user_id, file_id, size
        )

        total = await db.fetchval(
            "SELECT COUNT(*) FROM files WHERE user_id=$1",
            user_id
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Create Pack", callback_data="create")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])

        await message.reply(
            f"Total File: {total}",
            reply_markup=keyboard
        )

    except Exception as e:
        await message.reply(f"Error:\n{e}")
        print("UPLOAD ERROR:", e)

# ================= CALLBACK =================

@app.on_callback_query()
async def callback(client, cb):
    user_id = cb.from_user.id

    if cb.data == "cancel":
        await db.execute("DELETE FROM files WHERE user_id=$1", user_id)
        await cb.message.edit("Upload dibatalkan.")
        return

    if cb.data == "create":
        code = generate_code()

        await db.execute(
            "INSERT INTO packs(user_id,code) VALUES($1,$2)",
            user_id, code
        )

        bot_username = (await app.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"

        await cb.message.edit(
            f"✅ Pack berhasil dibuat\n\n"
            f"🔗 LINK:\n{link}\n\n"
            f"🔑 CODE:\n{code}"
        )
        return

    if cb.data.startswith("page_"):
        _, code, page = cb.data.split("_")
        await send_pack(cb.message, code, int(page))

# ================= SEND PACK =================

async def send_pack(message, code, page):
    user_id = message.from_user.id

    pack = await db.fetchrow("SELECT * FROM packs WHERE code=$1", code)
    if not pack:
        return await message.reply("Code tidak ditemukan.")

    if not await is_joined(user_id):
        return await message.reply(
            "Silakan join dulu 👇",
            reply_markup=join_button()
        )

    files = await db.fetch(
        "SELECT file_id FROM files WHERE user_id=$1",
        pack["user_id"]
    )

    if not files:
        return await message.reply("Tidak ada file.")

    per_page = 10
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    total_pages = (len(files) + per_page - 1) // per_page

    for f in files[start_index:end_index]:
        await app.send_video(user_id, f["file_id"])

    buttons = []

    if page > 1:
        buttons.append(
            InlineKeyboardButton("⬅ Prev", callback_data=f"page_{code}_{page-1}")
        )

    if page < total_pages:
        buttons.append(
            InlineKeyboardButton("Next ➡", callback_data=f"page_{code}_{page+1}")
        )

    if buttons:
        await message.reply(
            f"Page {page}/{total_pages}",
            reply_markup=InlineKeyboardMarkup([buttons])
        )

# ================= BROADCAST =================

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(client, message):
    if len(message.text.split()) < 2:
        return await message.reply("Masukkan pesan broadcast.")

    text = message.text.split(None, 1)[1]
    users = await db.fetch("SELECT user_id FROM users")

    for u in users:
        try:
            await app.send_message(u["user_id"], text)
        except:
            pass

    await message.reply("Broadcast selesai.")

# ================= RUN =================

async def main():
    await connect_db()
    await create_tables()
    await app.start()
    print("Bot Running...")
    await idle()

asyncio.get_event_loop().run_until_complete(main())
