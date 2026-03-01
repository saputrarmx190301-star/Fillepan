import os
import sqlite3
import random
import string
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

raw_storage = os.getenv("STORAGE_CHANNEL")
if raw_storage.startswith("-100"):
    STORAGE_CHANNEL = int(raw_storage)
else:
    STORAGE_CHANNEL = raw_storage

FORCE_GROUP = os.getenv("FORCE_GROUP")

app = Client(
    "pro_file_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================= DATABASE =================
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("""
CREATE TABLE IF NOT EXISTS files (
code TEXT PRIMARY KEY,
file_ids TEXT,
total_size INTEGER,
file_names TEXT
)
""")
conn.commit()

# ================= MEMORY =================
user_files = {}
user_progress_msg = {}
user_pages = {}

# ================= UTIL =================
def generate_code(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def format_size(size):
    for unit in ['B','KB','MB','GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

async def safe_forward(message):
    while True:
        try:
            return await message.forward(STORAGE_CHANNEL)
        except FloodWait as e:
            await asyncio.sleep(e.value)

async def safe_copy(client, user_id, msg_id):
    while True:
        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=STORAGE_CHANNEL,
                message_id=int(msg_id)
            )
            break
        except FloodWait as e:
            await asyncio.sleep(e.value)

async def check_join(client, user_id):
    if not FORCE_GROUP:
        return True
    try:
        member = await client.get_chat_member(FORCE_GROUP, user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]
    except:
        return False

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()

    args = message.command

    if len(args) > 1:
        code = args[1]

        if not await check_join(client, user_id):
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Join Group", url=f"https://t.me/{FORCE_GROUP.replace('@','')}")],
                [InlineKeyboardButton("🔄 Check Again", url=f"https://t.me/{(await client.get_me()).username}?start={code}")]
            ])
            return await message.reply("⚠️ Join group dulu!", reply_markup=btn)

        cursor.execute("SELECT file_ids,total_size,file_names FROM files WHERE code=?", (code,))
        data = cursor.fetchone()
        if not data:
            return await message.reply("❌ Code tidak ditemukan.")

        file_ids = data[0].split(",")
        total_size = data[1]
        file_names = data[2].split("||")

        user_pages[user_id] = {
            "ids": file_ids,
            "size": total_size,
            "names": file_names
        }

        await send_page(client, user_id, 1)
        return

    await message.reply("👋 Kirim media lalu ketik /create untuk buat link.")

# ================= HANDLE MEDIA =================
@app.on_message(filters.private & filters.media)
async def handle_media(client, message):
    user_id = message.from_user.id

    try:
        forwarded = await safe_forward(message)
    except Exception as e:
        return await message.reply(f"❌ Gagal upload:\n{e}")

    await asyncio.sleep(0.3)

    file_size = 0
    file_name = "Unknown"

    if message.video:
        file_size = message.video.file_size
        file_name = message.video.file_name or "video.mp4"
    elif message.document:
        file_size = message.document.file_size
        file_name = message.document.file_name or "file.bin"
    elif message.audio:
        file_size = message.audio.file_size
        file_name = message.audio.file_name or "audio.mp3"

    if user_id not in user_files:
        user_files[user_id] = []

    user_files[user_id].append({
        "msg_id": forwarded.id,
        "size": file_size,
        "name": file_name
    })

    total_files = len(user_files[user_id])
    total_size = sum(f["size"] for f in user_files[user_id])

    if user_id in user_progress_msg:
        try:
            await user_progress_msg[user_id].delete()
        except:
            pass

    msg = await message.reply(
        f"📤 Upload Progress\n\n"
        f"📁 Total Media: {total_files}\n"
        f"💾 Total Size: {format_size(total_size)}\n\n"
        f"Ketik /create untuk membuat link."
    )

    user_progress_msg[user_id] = msg

# ================= CREATE =================
@app.on_message(filters.command("create"))
async def create_link(client, message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        return await message.reply("❌ Tidak ada media.")

    code = generate_code()

    file_ids = []
    total_size = 0
    file_names = []

    for f in user_files[user_id]:
        file_ids.append(str(f["msg_id"]))
        total_size += f["size"]
        file_names.append(f["name"])

    cursor.execute(
        "INSERT INTO files VALUES (?,?,?,?)",
        (code, ",".join(file_ids), total_size, "||".join(file_names))
    )
    conn.commit()

    link = f"https://t.me/{(await client.get_me()).username}?start={code}"

    if user_id in user_progress_msg:
        try:
            await user_progress_msg[user_id].delete()
        except:
            pass

    del user_files[user_id]

    await message.reply(
        f"✅ Link berhasil dibuat!\n\n"
        f"📁 Total Media: {len(file_ids)}\n"
        f"💾 Total Size: {format_size(total_size)}\n\n"
        f"🔗 {link}\n\n"
        f"📌 Code:\n{code}"
    )

# ================= PAGINATION =================
async def send_page(client, user_id, page):
    data = user_pages[user_id]
    file_ids = data["ids"]
    file_names = data["names"]
    total_size = data["size"]

    per_page = 10
    total_pages = (len(file_ids) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page

    caption = (
        f"📁 Total Media: {len(file_ids)}\n"
        f"💾 Total Size: {format_size(total_size)}\n"
        f"📄 Page {page}/{total_pages}\n\n"
        f"Files:\n"
    )

    for i in range(start, min(end, len(file_names))):
        caption += f"{i+1}. {file_names[i]}\n"

    await client.send_message(user_id, caption)

    for msg_id in file_ids[start:end]:
        await safe_copy(client, user_id, msg_id)
        await asyncio.sleep(0.2)

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))

    if buttons:
        await client.send_message(
            user_id,
            "Navigation:",
            reply_markup=InlineKeyboardMarkup([buttons])
        )

@app.on_callback_query()
async def page_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        await callback_query.message.delete()
        await send_page(client, user_id, page)

# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Reply pesan dengan /broadcast")

    users = cursor.execute("SELECT user_id FROM users").fetchall()
    total = len(users)

    status = await message.reply(f"📢 Broadcast Dimulai...\nTotal: {total}")

    success = 0
    failed = 0

    for user in users:
        try:
            await message.reply_to_message.copy(user[0])
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await message.reply_to_message.copy(user[0])
                success += 1
            except:
                failed += 1
        except:
            failed += 1

        await asyncio.sleep(0.05)

    await status.edit_text(
        f"✅ Broadcast Selesai\n\n"
        f"Total: {total}\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )

# ================= RUN =================
app.run()
