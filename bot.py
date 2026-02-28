import os
import asyncio
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

app = Client("premium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= DATABASE =================
db = sqlite3.connect("database.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS files (code TEXT, file_id TEXT, size INTEGER)")
db.commit()

# ================= USER SESSIONS =================
user_sessions = {}  # {user_id: {"files":[], "progress":Message}}

# ================= UTIL =================
async def check_join(user_id):
    try:
        member = await app.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except:
        return False

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload File", callback_data="cmd_upload")],
        [InlineKeyboardButton("📊 Statistik", callback_data="stats")],
        [InlineKeyboardButton("📢 Channel Bot", url=CHANNEL_LINK)]
    ])

def format_progress(total_files, total_uploaded):
    bar_len = 20
    filled_len = int(bar_len * total_uploaded / total_files) if total_files else 0
    bar = "█" * filled_len + "░" * (bar_len - filled_len)
    return f"📦 Upload Progress: {total_uploaded}/{total_files}\n[{bar}]"

def format_size(total_bytes):
    return f"{round(total_bytes/1024/1024,2)} MB"

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    db.commit()

    if not await check_join(user_id):
        return await message.reply(
            "🔒 Silakan join channel terlebih dahulu.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)]])
        )

    args = message.text.split()
    if len(args) > 1:
        return await send_files(user_id, args[1])

    await message.reply(
        "👋 Welcome to Ultra Premium File Bot\n\nGunakan menu di bawah:",
        reply_markup=main_menu()
    )

# ================= COMMANDS =================
@app.on_message(filters.command("upload"))
async def cmd_upload(client, message):
    user_id = message.from_user.id
    user_sessions[user_id] = {"files": [], "progress": None}
    await message.reply("📤 Kirim file / video sekarang. Progress realtime akan muncul.")

@app.on_message(filters.command("mycode"))
async def cmd_mycode(client, message):
    cursor.execute("SELECT DISTINCT code FROM files")
    results = cursor.fetchall()
    if not results:
        return await message.reply("❌ Kamu belum membuat pack apapun.")
    codes = "\n".join([x[0] for x in results])
    await message.reply(f"📦 Pack kamu:\n{codes}")

@app.on_message(filters.command("account"))
async def cmd_account(client, message):
    cursor.execute("SELECT COUNT(*) FROM files")
    total_files = cursor.fetchone()[0]
    await message.reply(f"👤 Info Akun\n\nTotal File: {total_files}")

@app.on_message(filters.command("channelbot"))
async def cmd_channelbot(client, message):
    await message.reply(
        "📢 Channel Bot:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)]])
    )

# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    # Broadcast text: /broadcast Pesan
    text = message.text.split(" ", 1)
    if len(text) < 2 and not message.reply_to_message:
        return await message.reply("❌ Gunakan /broadcast <pesan> atau reply pesan media/text")
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0
    if message.reply_to_message:
        # broadcast media
        for user in users:
            try:
                await message.reply_to_message.copy(user[0])
                await asyncio.sleep(0.05)
                sent += 1
            except:
                pass
    else:
        # broadcast text
        msg_text = text[1]
        for user in users:
            try:
                await client.send_message(user[0], msg_text)
                await asyncio.sleep(0.05)
                sent += 1
            except:
                pass
    await message.reply(f"✅ Broadcast selesai.\nTerkirim: {sent}")

# ================= UPLOAD FILE =================
@app.on_message(filters.video | filters.document)
async def handle_media(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return
    session = user_sessions[user_id]

    forwarded = await message.forward(STORAGE_CHANNEL)
    if message.video:
        file_id = forwarded.video.file_id
        size = forwarded.video.file_size
    else:
        file_id = forwarded.document.file_id
        size = forwarded.document.file_size

    session["files"].append((file_id, size))

    # Update progress realtime
    total_files = len(session["files"])
    total_size = sum(x[1] for x in session["files"])
    text = f"{format_progress(total_files,total_files)}\n💾 {format_size(total_size)}\nKlik /create untuk membuat link."

    if session["progress"]:
        await session["progress"].edit(text)
    else:
        msg = await message.reply(text)
        session["progress"] = msg

# ================= CREATE PACK =================
@app.on_message(filters.command("create"))
async def cmd_create(client, message):
    user_id = message.from_user.id
    if user_id not in user_sessions or not user_sessions[user_id]["files"]:
        return await message.reply("❌ Tidak ada file.")

    code = str(uuid.uuid4())[:8]
    session = user_sessions[user_id]

    for file_id, size in session["files"]:
        cursor.execute("INSERT INTO files VALUES (?, ?, ?)", (code, file_id, size))
    db.commit()

    bot_username = (await app.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.reply(f"🎉 Pack Created!\n\n🔗 {link}\n\n🔑 `{code}`", disable_web_page_preview=True)

    # Delete progress message
    if session.get("progress"):
        await session["progress"].delete()
    del user_sessions[user_id]

# ================= SEND FILES + PAGINATION =================
async def send_files(user_id, code, page=1):
    cursor.execute("SELECT file_id FROM files WHERE code=?", (code,))
    results = cursor.fetchall()
    if not results:
        return
    files = [x[0] for x in results]
    per_page = 10
    total_pages = (len(files)+per_page-1)//per_page

    start = (page-1)*per_page
    end = start+per_page
    for file_id in files[start:end]:
        try:
            await app.send_cached_media(user_id, file_id)
            await asyncio.sleep(0.3)
        except FloodWait as e:
            await asyncio.sleep(e.value)

    # Pagination buttons
    if total_pages <= 1:
        return
    buttons=[]
    if page>1:
        buttons.append(InlineKeyboardButton("⬅", callback_data=f"{code}|{page-1}"))
    for p in range(1,total_pages+1):
        buttons.append(InlineKeyboardButton(f"[{p}]" if p==page else str(p), callback_data=f"{code}|{p}"))
    if page<total_pages:
        buttons.append(InlineKeyboardButton("➡", callback_data=f"{code}|{page+1}"))

    buttons.append(InlineKeyboardButton("📢 Channel Bot", url=CHANNEL_LINK))
    await app.send_message(user_id, "📂 Pilih halaman:", reply_markup=InlineKeyboardMarkup([buttons]))

# ================= CALLBACK =================
@app.on_callback_query()
async def callback(client, cb):
    data = cb.data
    if "|" in data:
        code,page=data.split("|")
        await send_files(cb.from_user.id,code,int(page))
        return await cb.answer()
    if data=="stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        users=cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT code) FROM files")
        packs=cursor.fetchone()[0]
        await cb.message.edit(f"📊 Statistik\n\n👥 Users: {users}\n📦 Packs: {packs}",reply_markup=main_menu())
        await cb.answer()
    if data=="cmd_upload":
        await cmd_upload(client,cb.message)

# ================= DETECT CODE =================
@app.on_message(filters.text & ~filters.command(["start","create","upload","mycode","account","channelbot","broadcast"]))
async def detect_code(client,message):
    await send_files(message.from_user.id,message.text.strip())

# ================= RUN =================
app.run()
