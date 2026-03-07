import sqlite3

conn = sqlite3.connect("files.db", check_same_thread=False)
db = conn.cursor()

db.execute("""
CREATE TABLE IF NOT EXISTS files(
file_key TEXT,
message_id INTEGER
)
""")

conn.commit()


def save_file(key, msg_id):
    db.execute("INSERT INTO files VALUES (?,?)", (key, msg_id))
    conn.commit()


def get_file(key):
    db.execute("SELECT message_id FROM files WHERE file_key=?", (key,))
    data = db.fetchone()
    return data
