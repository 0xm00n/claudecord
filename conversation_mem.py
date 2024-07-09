from typing import List, Dict, Optional
import aiosqlite
import json
import logging


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class ConversationStorage:
    def __init__(self, db_path: str):
        self.db_path: str = db_path
        self.db: Optional[aiosqlite.Connection] = None
        self.logger: logging.Logger = logging.getLogger(__name__)

    async def init(self) -> None:
        self.db = await aiosqlite.connect(self.db_path)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                user_id TEXT PRIMARY KEY,
                history TEXT NOT NULL
            )
        """)
        await self.db.commit()
        self.logger.info(f"SQLite database initialized at {self.db_path}")

    async def get_convo(self, user_id: str) -> List[Dict[str, str]]:
        try:
            async with self.db.execute("SELECT history FROM conversations WHERE user_id = ?", (user_id,)) as cursor:
                result: Optional[tuple] = await cursor.fetchone()
                if result:
                    return json.loads(result[0])
        except Exception as e:
            self.logger.error(f"Error retrieving conversation for user {user_id}: {e}")
        return []

    async def update_convo(self, user_id: str, conversation: List[Dict[str, str]]) -> None:
        try:
            await self.db.execute(
                "INSERT OR REPLACE INTO conversations (user_id, history) VALUES (?, ?)",
                (user_id, json.dumps(conversation))
            )
            await self.db.commit()
            self.logger.debug(f"Updated conversation for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error updating conversation for user {user_id}: {e}")

    async def delete_convo(self, user_id: str) -> None:
        try:
            await self.db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            await self.db.commit()
            self.logger.debug(f"Deleted conversation for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error deleting conversation for user {user_id}: {e}")

    async def close(self) -> None:
        if self.db:
            await self.db.close()
            self.logger.info("Database connection closed")





