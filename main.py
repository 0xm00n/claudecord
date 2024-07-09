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

# logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# load environment variables
load_dotenv()

# Constants
DISCORD_TOK: Final[str] = os.getenv('DISCORD_TOKEN')
CLAUDE_KEY: Final[str] = os.getenv('ANTHROPIC_API_KEY')
MODEL_NAME: Final[str] = "claude-3-opus-20240229"
MAX_TOKENS: Final[int] = 4096
TEMPERATURE: Final[float] = 0.1
MAX_MEMORY: Final[int] = 20
SYSTEM_PROMPT: Final[str] = """
You are a world-class expert in theoretical ML research, computational neuroscience, and cognitive science 
with extensive experience in engineering complex ML systems end-to-end in production. Respond with concise 
answers backed by rigorous mathematics and theory. Make sure to double check your math and logic for 
correctness and consistency rigorously before answering. Finally, back up the choices you make with a deep, 
specific rationale rather than vague, general answers. When analyzing scientific papers, provide citations 
for your statements.
""".strip()

# initialize clients
intents: Intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)
claude_client: AsyncAnthropic = AsyncAnthropic(api_key=CLAUDE_KEY)

# initialize conversation storage
storage = ConversationStorage("conversations.db")

async def get_claude_response(user_id: str, new_content: List[Dict[str, any]]) -> str:
    try:
        conversation: List[Dict[str, any]] = await storage.get_convo(user_id)
        
        # process attachment references
        for item in new_content:
            if item['type'] == 'image' and item['source']['type'] == 'attachment_ref':
                attachment_id = item['source']['attachment_id']
                filename, content = await storage.get_attachment(attachment_id)
                item['source'] = {"type": "base64", "media_type": "image/png", "data": content}
        
        # add the new content to the conversation
        conversation.append({"role": "user", "content": new_content})
        
        # trim the conversation if it's too long
        if len(conversation) > MAX_MEMORY:
            conversation = conversation[-(MAX_MEMORY - (MAX_MEMORY % 2)):]
        
        msg = await claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=SYSTEM_PROMPT,
            messages=conversation
        )
        
        assistant_response: str = msg.content[0].text
        
        # add Claude's response to the conversation
        conversation.append({"role": "assistant", "content": assistant_response})
        
        # update the entire conversation in the database
        await storage.update_convo(user_id, conversation)
        
        logger.debug(f"Processed message for user {user_id}")
        logger.debug(f"Conversation history: {conversation}")
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
        claude_response: str = await get_claude_response(str(msg.author.id), content)
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
        

        reading_msg = await msg.channel.send("reading your attachments 🔎...")

        # process attachments
        for attachment in msg.attachments:
            attachment_content = await process_file(attachment, str(msg.author.id), storage)
            content.extend(attachment_content)
        
        await reading_msg.delete()

        if content:
            await send_msg(msg, content)
        else:
            await msg.channel.send("Please provide some text, images, or files for me to analyze.")
    
    await bot.process_commands(msg)

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
