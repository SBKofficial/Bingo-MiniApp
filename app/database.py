import aiosqlite
import asyncio

DB_NAME = "bingo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'WAITING',
    entry_fee INTEGER NOT NULL,
    prize_pool INTEGER NOT NULL,
    called_numbers TEXT DEFAULT '[]',
    winner_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS participants (
    match_id INTEGER,
    user_id INTEGER,
    grid_layout TEXT NOT NULL,
    marked_cells TEXT DEFAULT '[]',
    player_index INTEGER,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id, user_id)
);
"""

async def init_db():
    print("⏳ Connecting to SQLite...")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executescript(SCHEMA)
        await db.execute("PRAGMA journal_mode=WAL;") 
        await db.commit()
    print("✅ Database ready!")

if __name__ == "__main__":
    asyncio.run(init_db())
  
