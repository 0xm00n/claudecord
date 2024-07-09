from typing import List, Dict, Optional, Tuple
import aiosqlite
import json
import logging


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ConversationStorage:
    def __init__(self, db_path: str):
        self.db_path: str = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    user_id TEXT PRIMARY KEY,
                    history TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    filename TEXT,
                    content BLOB
                )
            """)
            await db.commit()

    async def get_convo(self, user_id: str) -> List[Dict[str, any]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT history FROM conversations WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return json.loads(result[0])
        return []

    async def update_convo(self, user_id: str, conversation: List[Dict[str, any]]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO conversations (user_id, history) VALUES (?, ?)",
                (user_id, json.dumps(conversation))
            )
            await db.commit()

    async def store_attachment(self, user_id: str, filename: str, content: bytes) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO attachments (user_id, filename, content) VALUES (?, ?, ?)",
                (user_id, filename, content)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_attachment(self, attachment_id: int) -> Tuple[str, bytes]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT filename, content FROM attachments WHERE id = ?", (attachment_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result
        return None

    async def delete_user_convo(self, user_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM attachments WHERE user_id = ?", (user_id,))
            await db.commit()
