from typing import List, Dict, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()
MONGODB_URI = os.getenv('MONGODB_URI')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ConversationStorage:
    def __init__(self, db_name: str):
        # Connect to MongoDB
        self.client = AsyncIOMotorClient(MONGODB_URI)
        self.db = self.client[db_name]
        
        # Collections
        self.messages = self.db.channel_messages
        self.attachments = self.db.attachments

    async def init(self) -> None:
        """Initialize indexes for better query performance if they don't exist"""
        try:
            # Get existing indexes
            message_indexes = await self.messages.list_indexes().to_list(None)
            attachment_indexes = await self.attachments.list_indexes().to_list(None)
            
            # Convert to set of index names for easy checking
            message_index_names = {idx.get('name') for idx in message_indexes}
            attachment_index_names = {idx.get('name') for idx in attachment_indexes}
            
            # Create message indexes if they don't exist
            if 'channel_id_1' not in message_index_names:
                await self.messages.create_index([("channel_id", 1)])
                logger.info("Created channel_id index")
                
            if 'channel_id_1_timestamp_-1' not in message_index_names:
                await self.messages.create_index([("channel_id", 1), ("timestamp", -1)])
                logger.info("Created channel_id_timestamp index")
                
            if 'message_id_1' not in message_index_names:
                await self.messages.create_index("message_id", unique=True)
                logger.info("Created message_id index")
            
            # Create attachment indexes if they don't exist
            if 'attachment_id_1' not in attachment_index_names:
                await self.attachments.create_index("attachment_id", unique=True)
                logger.info("Created attachment_id index")
                
            if 'user_id_1' not in attachment_index_names:
                await self.attachments.create_index("user_id")
                logger.info("Created user_id index")
            
            logger.info("MongoDB indexes verification complete")
        except Exception as e:
            logger.error(f"Error verifying/creating MongoDB indexes: {e}")
            raise

    async def get_convo(self, channel_id: str) -> List[Dict[str, any]]:
        """Get recent message history for a channel"""
        try:
            cursor = self.messages.find(
                {'channel_id': channel_id}
            ).sort('timestamp', -1).limit(20)
            
            messages = await cursor.to_list(length=20)
            return list(reversed(messages))  # Return in chronological order
        except Exception as e:
            logger.error(f"Error getting channel history: {e}")
            return []

    async def update_convo(self, channel_id: str, message: Dict[str, any]) -> None:
        """Store a message in the channel history"""
        try:
            message_doc = {
                'message_id': message.get('message_id'),
                'channel_id': channel_id,
                'author': {
                    'user_id': message.get('author', {}).get('user_id'),
                    'username': message.get('author', {}).get('username'),
                    'is_bot': message.get('author', {}).get('is_bot', False)
                },
                'content': message.get('content'),
                'timestamp': datetime.utcnow()
            }
            await self.messages.insert_one(message_doc)
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            raise

    async def store_attachment(self, user_id: str, filename: str, content: bytes) -> int:
        """Store an attachment and return its ID"""
        try:
            # Convert bytes to base64 for MongoDB storage
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            result = await self.attachments.insert_one({
                'user_id': user_id,
                'filename': filename,
                'content': content_b64,
                'timestamp': datetime.utcnow()
            })
            
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error storing attachment: {e}")
            raise

    async def get_attachment(self, attachment_id: int) -> Optional[Tuple[str, bytes]]:
        """Retrieve an attachment by its ID"""
        try:
            doc = await self.attachments.find_one({'_id': attachment_id})
            if doc:
                content = base64.b64decode(doc['content'])
                return (doc['filename'], content)
            return None
        except Exception as e:
            logger.error(f"Error retrieving attachment: {e}")
            return None

    async def delete_channel_convo(self, channel_id: str) -> None:
        """Delete all messages in a channel"""
        try:
            result = await self.messages.delete_many({'channel_id': channel_id})
            logger.info(f"Deleted {result.deleted_count} messages from channel {channel_id}")
        except Exception as e:
            logger.error(f"Error deleting channel data: {e}")
            raise

    async def delete_user_convo(self, user_id: str) -> None:
        """Delete all data associated with a user and related bot responses"""
        try:
            # Get all message IDs from the user
            user_messages = await self.messages.find(
                {'author.user_id': user_id},
                {'message_id': 1}
            ).to_list(length=None)
            
            # Extract message IDs
            message_ids = [msg['message_id'] for msg in user_messages]
            
            # Delete user's messages
            await self.messages.delete_many({'author.user_id': user_id})
            
            # Delete Claude's responses to user's messages
            for msg_id in message_ids:
                await self.messages.delete_one({
                    'message_id': f'claude_{msg_id}'
                })
            
            # Delete user's attachments
            await self.attachments.delete_many({'user_id': user_id})
            
            logger.info(f"Deleted all data for user {user_id} and related bot responses")
        except Exception as e:
            logger.error(f"Error deleting user data: {e}")
            raise
