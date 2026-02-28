import os
import sqlite3
import random
import string
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
STORAGE_CHANNEL = int(os.environ.get("STORAGE_CHANNEL"))
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
FORCE_GROUP = os.getenv("FORCE_GROUP")

app = Client("pro_file_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= DATABASE =================
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS files (code TEXT PRIMARY KEY, file_ids TEXT)")
conn.commit()

# ================= MEMORY =================
user_files = {}
broadcast_mode = False

# ================= UTIL =================
def generate_code(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

async def check_join(client, user_id):
    if not FORCE_GROUP:
        return True
    try:
        member = await client.get_chat_member(FORCE_GROUP, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False
        
        # ================= JOIN BUTTON =================
def join_button():
    if not FORCE_GROUP:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Telegram", url=f"https://t.me/{FORCE_GROUP.replace('@','')}")]
    ])

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id

    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()

    args = message.command

    if len(args) > 1:
        code = args[1]

        joined = await check_join(client, user_id)
        if not joined:
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

        await message.reply("📂 Mengirim file...")

        for msg_id in file_ids:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=STORAGE_CHANNEL,
                message_id=int(msg_id)
            )

        await message.reply(
    "✅ Selesai!",
    reply_markup=join_button()
)
return

    await message.reply("👋 Kirim file lalu tekan /create untuk membuat link.")

# ================= HANDLE FILE =================
@app.on_message(filters.private & filters.media)
async def handle_files(client, message):
    user_id = message.from_user.id

    try:
        forwarded = await message.forward(STORAGE_CHANNEL)
    except Exception as e:
        return await message.reply(f"❌ Gagal upload:\n{e}")

    if user_id not in user_files:
        user_files[user_id] = []

    user_files[user_id].append(str(forwarded.id))

    await message.reply(
    "👋 Kirim file lalu tekan /create untuk membuat link.",
    reply_markup=join_button()
    )
# ================= CREATE LINK =================
@app.on_message(filters.command("create"))
async def create_link(client, message):
    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        return await message.reply("❌ Tidak ada file.")

    code = generate_code()
    file_ids = ",".join(user_files[user_id])

    cursor.execute("INSERT INTO files VALUES (?,?)", (code, file_ids))
    conn.commit()

    link = f"https://t.me/{(await client.get_me()).username}?start={code}"

    del user_files[user_id]

    await message.reply(
        f"✅ Link berhasil dibuat!\n\n🔗 {link}\n\n📌 Code:\n{code}"
    )

# ================= MANUAL CODE =================
@app.on_message(filters.private & filters.text & ~filters.command(["start","create","broadcast"]))
async def manual_code(client, message):
    global broadcast_mode

    if message.from_user.id == ADMIN_ID and broadcast_mode:
        broadcast_mode = False
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

        sent = 0
        for user in users:
            try:
                await message.copy(user[0])
                sent += 1
            except:
                pass

        return await message.reply(f"✅ Broadcast terkirim ke {sent} user.")

    code = message.text.strip()

    cursor.execute("SELECT file_ids FROM files WHERE code=?", (code,))
    data = cursor.fetchone()

    if not data:
        return

    file_ids = data[0].split(",")

    for msg_id in file_ids:
    await client.copy_message(
        chat_id=message.from_user.id,
        from_chat_id=STORAGE_CHANNEL,
        message_id=int(msg_id)
    )

await message.reply(
    "✅ Semua file berhasil dikirim.",
    reply_markup=join_button()
                )
# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    global broadcast_mode
    broadcast_mode = True
    await message.reply("📢 Kirim pesan yang ingin dibroadcast.")

# ================= RUN =================
app.run()
