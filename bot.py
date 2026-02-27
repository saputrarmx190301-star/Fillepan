from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import string
import asyncio
import asyncpg
from config import *

app = Client(
    "bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

db = None

async def connect_db():
    global db
    db = await asyncpg.connect(DATABASE_URL)

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.on_message(filters.video)
async def upload_video(client, message):
    user_id = message.from_user.id
    
    forwarded = await message.forward(STORAGE_CHANNEL)
    file_id = forwarded.video.file_id
    size = forwarded.video.file_size

    await db.execute(
        "INSERT INTO files(user_id,file_id,size) VALUES($1,$2,$3)",
        user_id, file_id, size
    )

    total = await db.fetchval(
        "SELECT COUNT(*) FROM files WHERE user_id=$1",
        user_id
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Create", callback_data="create")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

    await message.reply(
        f"Total File: {total}\nSize: updating...",
        reply_markup=keyboard
    )

@app.on_callback_query()
async def callback(client, callback_query):
    user_id = callback_query.from_user.id

    if callback_query.data == "create":
        code = generate_code()
        await db.execute(
            "INSERT INTO packs(user_id,code) VALUES($1,$2)",
            user_id, code
        )

        link = f"https://t.me/{(await app.get_me()).username}?start={code}"

        await callback_query.message.edit(
            f"LINK:\n{link}\n\nCODE:\n{code}"
        )

    if callback_query.data == "cancel":
        await db.execute("DELETE FROM files WHERE user_id=$1", user_id)
        await callback_query.message.edit("Upload dibatalkan.")
