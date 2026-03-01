import os
import sqlite3
import random
import string
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

raw_storage = os.getenv("STORAGE_CHANNEL")
if raw_storage.startswith("-100"):
    STORAGE_CHANNEL = int(raw_storage)
else:
    STORAGE_CHANNEL = raw_storage

FORCE_GROUP = os.getenv("FORCE_GROUP")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

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
cursor.execute("CREATE TABLE IF NOT EXISTS files (code TEXT PRIMARY KEY, file_ids TEXT)")
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

        cursor.execute("SELECT file_ids FROM files WHERE code=?", (code,))
        data = cursor.fetchone()
        if not data:
            return await message.reply("❌ Code tidak ditemukan.")

        file_ids = data[0].split(",")
        user_pages[user_id] = file_ids
        await send_page(client, user_id, file_ids, 1)
        return

    await message.reply("👋 Kirim media lalu ketik /create untuk buat link.")

# ================= HANDLE MEDIA =================
@app.on_message(filters.private & filters.media)
async def handle_media(client, message):
    user_id = message.from_user.id

    try:
        forwarded = await message.forward(STORAGE_CHANNEL)
    except Exception as e:
        return await message.reply(f"❌ Gagal upload:\n{e}")

    file_size = 0
    if message.video:
        file_size = message.video.file_size
    elif message.document:
        file_size = message.document.file_size
    elif message.audio:
        file_size = message.audio.file_size

    if user_id not in user_files:
        user_files[user_id] = []

    user_files[user_id].append({
        "msg_id": forwarded.id,
        "size": file_size
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

# ================= CREATE LINK =================
@app.on_message(filters.command("create"))
async def create_link(client, message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        return await message.reply("❌ Tidak ada media.")

    code = generate_code()
    file_ids = [str(f["msg_id"]) for f in user_files[user_id]]

    cursor.execute("INSERT INTO files VALUES (?,?)", (code, ",".join(file_ids)))
    conn.commit()

    link = f"https://t.me/{(await client.get_me()).username}?start={code}"

    if user_id in user_progress_msg:
        try:
            await user_progress_msg[user_id].delete()
        except:
            pass

    del user_files[user_id]

    await message.reply(f"✅ Link berhasil dibuat!\n\n🔗 {link}")

# ================= PAGINATION =================
async def send_page(client, user_id, file_ids, page=1):
    per_page = 10
    total_pages = (len(file_ids) + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page

    for msg_id in file_ids[start:end]:
        await client.copy_message(
            chat_id=user_id,
            from_chat_id=STORAGE_CHANNEL,
            message_id=int(msg_id)
        )

    buttons = []

    if page > 1:
        buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))

    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))

    await client.send_message(
        user_id,
        f"📄 Page {page}/{total_pages}",
        reply_markup=InlineKeyboardMarkup([buttons]) if buttons else None
    )

@app.on_callback_query()
async def page_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        file_ids = user_pages.get(user_id)

        if not file_ids:
            return await callback_query.answer("Session expired", show_alert=True)

        await callback_query.message.delete()
        await send_page(client, user_id, file_ids, page)

# ================= RUN =================
app.run()
