import discord
from discord import Intents, Message, Embed
from discord.ext import commands
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from typing import Final, List, Dict
import asyncio
import logging
import os
from io import BytesIO

from conversation_mem import ConversationStorage
from multimodal import process_file
from rag import RagProcessor

# Configure logging - only show INFO and above for most modules
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Keep discord.py at INFO level
logger = logging.getLogger(__name__)

# load environment variables
load_dotenv()

# Constants
DISCORD_TOK: Final[str] = os.getenv('DISCORD_TOKEN')
CLAUDE_KEY: Final[str] = os.getenv('ANTHROPIC_API_KEY')
MODEL_NAME: Final[str] = "claude-3-5-sonnet-20241022"
MAX_TOKENS: Final[int] = 4096
TEMPERATURE: Final[float] = 0.1
MAX_MEMORY: Final[int] = 20 

# System prompt for normal mode (non-RAG) conversations
SYSTEM_PROMPT: Final[str] = """
You are a world-class expert in theoretical ML research, computational neuroscience, cognitive science,
philosophy, and psychology with extensive experience in engineering complex ML systems end-to-end in 
production. Respond with concise answers backed by rigorous mathematics, theory, and philosophical 
reasoning. Make sure to double check your math, logic, and philosophical arguments for correctness 
and consistency rigorously before answering.

Your answers must be concise but detailed in technical specificity while avoiding any generic fluff.
Note: For research paper analysis, use >rag command to enable RAG mode instead.
""".strip()

# test mode flag
TEST_MODE: bool = False

# initialize clients
intents: Intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)
claude_client: AsyncAnthropic = AsyncAnthropic(api_key=CLAUDE_KEY)

# initialize conversation storage and RAG processor
storage = ConversationStorage("test_conversations.db" if TEST_MODE else "conversations.db")
rag_processor = RagProcessor()

# track which users are in RAG mode
rag_mode_users: set = set()

def log_conversation_state(conversation: List[Dict[str, any]], stage: str) -> None:
    """Debug helper to log conversation state at various stages"""
    if TEST_MODE:
        logger.debug(f"\n=== Conversation State at {stage} ===")
        logger.debug(f"Length: {len(conversation)} messages")
        for i, msg in enumerate(conversation):
            logger.debug(f"Message {i}:")
            logger.debug(f"  Role: {msg['role']}")
            logger.debug(f"  Content: {msg['content']}")
        logger.debug("=====================================\n")

async def get_claude_response(user_id: str, new_content: List[Dict[str, any]]) -> str:
    """Handle normal mode (non-RAG) conversations"""
    try:
        conversation: List[Dict[str, any]] = await storage.get_convo(user_id)
        log_conversation_state(conversation, "Initial Load")
        
        # process attachment references
        for item in new_content:
            if item['type'] == 'image' and item['source']['type'] == 'attachment_ref':
                attachment_id = item['source']['attachment_id']
                filename, content = await storage.get_attachment(attachment_id)
                item['source'] = {"type": "base64", "media_type": "image/png", "data": content}
        
        # add the new content to the conversation with proper structure
        conversation.append({"role": "user", "content": new_content})
        log_conversation_state(conversation, "After Adding User Message")
        
        # ensure conversation length is even (user-assistant pairs) and within limits
        if len(conversation) > MAX_MEMORY:
            # keep an even number of messages, starting with the most recent
            num_pairs = (MAX_MEMORY // 2) - 1  # subtract 1 to make room for the new pair
            conversation = conversation[-(num_pairs * 2):]
            logger.debug(f"Trimmed conversation to {len(conversation)} messages ({num_pairs} complete pairs)")
        
        log_conversation_state(conversation, "After Trimming")
    
        messages = []
        for msg in conversation:
            if isinstance(msg['content'], str):
                msg['content'] = [{"type": "text", "text": msg['content']}]
            messages.append(msg)
        
        log_conversation_state(messages, "Before API Call")
        
        msg = await claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=SYSTEM_PROMPT,
            messages=messages
        )
        
        assistant_response: str = msg.content[0].text
        
        # add Claude's response to the conversation with proper structure
        conversation.append({
            "role": "assistant",
            "content": [{"type": "text", "text": assistant_response}]
        })
        
        log_conversation_state(conversation, "After Adding Assistant Response")
        
        # update the entire conversation in the database
        await storage.update_convo(user_id, conversation)
        
        logger.debug(f"Processed message for user {user_id}")
        return assistant_response
    except Exception as e:
        logger.error(f"Error in get_claude_response: {e}")
        raise

async def send_msg(msg: Message, content: List[Dict[str, any]]) -> None:
    if not content:
        logger.warning('Content was empty.')
        return

    try:
        thinking_msg = await msg.channel.send("Thinking 🤔...")
        
        # Check if user is in RAG mode
        if str(msg.author.id) in rag_mode_users:
            # Extract text from content list
            text_content = " ".join([item["text"] for item in content if item["type"] == "text"])
            claude_response = await rag_processor.process_query(text_content)
        else:
            claude_response = await get_claude_response(str(msg.author.id), content)
            
        await thinking_msg.delete()
        
        # split the response into chunks of 2000 characters or less
        chunks = [claude_response[i:i+2000] for i in range(0, len(claude_response), 2000)]

        for chunk in chunks:
            embed = Embed(description=chunk, color=0xda7756)
            await msg.channel.send(embed=embed)
         
        logger.debug(f"Sent response to user {msg.author.id}")

    except Exception as e:
        logger.error(f"An error occurred in send_msg: {e}", exc_info=True)
        await msg.channel.send("I'm sorry, I encountered an error while processing your request.")

@bot.event
async def on_ready() -> None:
    logger.info(f'{bot.user} is now running...')
    await storage.init()
    
    if TEST_MODE:
        logger.info("=== RUNNING IN TEST MODE ===")
        logger.info(f"Max Memory: {MAX_MEMORY} messages ({MAX_MEMORY//2} pairs)")
        logger.info(f"Using test database: {storage.db_path}")
    
    # check if PyNaCl is installed
    try:
        import nacl
        logger.info("PyNaCl is installed. Voice support is available.")
    except ImportError:
        logger.warning("PyNaCl is not installed. Voice will NOT be supported.")

@bot.event
async def on_message(msg: Message) -> None:
    if msg.author == bot.user:
        return

    if bot.user.mentioned_in(msg):
        content = []
        
        # process text
        if msg.content:
            content.append({"type": "text", "text": msg.content})
        
        reading_msg = None
        if msg.attachments:
            reading_msg = await msg.channel.send("reading your attachments 🔎...")

        # process attachments - pass RAG processor and mode
        user_id = str(msg.author.id)
        is_rag_mode = user_id in rag_mode_users
        for attachment in msg.attachments:
            attachment_content = await process_file(
                attachment, 
                user_id, 
                storage,
                rag_processor=rag_processor if is_rag_mode else None,
                is_rag_mode=is_rag_mode
            )
            content.extend(attachment_content)
        
        if reading_msg:
            await reading_msg.delete()

        if content:
            await send_msg(msg, content)
        else:
            await msg.channel.send("Please provide some text, images, or files for me to analyze.")
    
    await bot.process_commands(msg)

@bot.command(name='rag')
async def toggle_rag(ctx):
    """Toggle RAG mode for research paper queries"""
    user_id = str(ctx.author.id)
    
    if user_id in rag_mode_users:
        rag_mode_users.remove(user_id)
        await ctx.send("RAG mode disabled. I will now respond normally to your queries.")
    else:
        rag_mode_users.add(user_id)
        await ctx.send("RAG mode enabled! I will now use research papers to answer your queries. You can:\n"
                      "1. Ask questions about papers in the local database\n"
                      "2. If local papers are insufficient, I'll search and analyze external papers\n"
                      "3. Attach PDF papers to add them to the local database\n"
                      "Use >rag again to disable RAG mode.")

@bot.command(name='delete_history')
async def delete_history(ctx):
    user_id = str(ctx.author.id)
    confirm_msg = await ctx.send("Are you sure you want to delete your entire conversation history? This action cannot be undone. Reply with 'y' to confirm.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'y'
    
    try:
        await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="Deletion cancelled. You did not confirm in time.")
    else:
        await storage.delete_user_convo(user_id)
        await ctx.send("Your conversation history has been deleted.")

async def main() -> None:
    try:
        await bot.start(DISCORD_TOK)
    except discord.LoginFailure:
        logger.error("Failed to log in. Please check your Discord token.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
