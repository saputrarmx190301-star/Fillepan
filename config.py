import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
OWNER_ID = int(os.getenv("OWNER_ID"))
STORAGE_CHANNEL = int(os.getenv("STORAGE_CHANNEL"))
DATABASE_URL = os.getenv("DATABASE_URL")

CHANNEL_LINK = os.getenv("CHANNEL_LINK")  # link group/channel untuk join
