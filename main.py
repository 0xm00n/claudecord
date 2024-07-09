
from discord import Intents, Client, Message, Embed
from conversation_mem import ConversationStorage
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from typing import Final

import asyncio
import aiohttp
import logging
import os


# logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# load env variables
load_dotenv()

# constants
DISCORD_TOK: Final[str] = os.getenv('DISCORD_TOKEN')
MAX_MEMORY: Final[int] = 20
CLAUDE_KEY: Final[str] = os.getenv('ANTHROPIC_API_KEY')
MODEL_NAME: Final[str] = "claude-3-5-sonnet-20240620"
MAX_TOKENS: Final[int] = 4096
TEMPERATURE: Final[float] = 0.1 
SYSTEM_PROMPT: Final[str] = """
You are a world-class expert in theoretical ML research, computational neuroscience, and cognitive science 
with extensive experience in engineering complex ML systems end-to-end in production. Respond with concise 
answers backed by rigorous mathematics and theory. Make sure to double check your math and logic for 
correctness and consistency rigorously before answering. Finally, back up the choices you make with a deep, 
specific rationale rather than vague, general answers.
""".strip()

# init clients
intents: Intents = Intents.default()
intents.message_content = True
discord_client: Client = Client(intents=intents)
claude_client: AsyncAnthropic = AsyncAnthropic(api_key=CLAUDE_KEY)

# init convo storage    
storage = ConversationStorage("conversations.db")

async def get_claude_response(user_id: str, user_input: str) -> str:
    conversation: List[Dict[str, str]] = await storage.get_convo(user_id)
    
    # add the new user message
    conversation.append({"role": "user", "content": user_input})
    
    # trim the conversation if it's too long, ensuring we keep an even number of messages
    # (alternating user and assistant messages)
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

async def send_msg(msg: Message, user_msg: str) -> None:
    if not user_msg:
        logger.warning('Msg was empty probably because intents were not enabled properly.')
        return

    try:
        thinking_msg = await msg.channel.send("Thinking...")
        claude_response: str = await get_claude_response(str(msg.author.id),user_msg)
        await thinking_msg.delete()
        
        # replace "\n" with actual newlines
        claude_response = claude_response.replace("\\n", "\n")
        
        # split the response into chunks of 2000 (discord single msg limit) characters or less
        # we use a list comprehension with splitlines() and join() to preserve newlines
        chunks = [""]
        for line in claude_response.splitlines(True):  # keepends=True to keep newline characters
            if len(chunks[-1]) + len(line) > 2000:
                chunks.append(line)
            else:
                chunks[-1] += line

        for chunk in chunks:
            # use discord.Embed for a nicer formatting
            embed = Embed(description=chunk, color=0xda7756)
            await msg.channel.send(embed=embed)
         
        logger.debug(f"Sent response to user {msg.author.id}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        await msg.channel.send("I'm sorry, I encountered an error while processing your request.")

@discord_client.event
async def on_ready() -> None:
    logger.info(f'{discord_client.user} is now running...')
    await storage.init()

@discord_client.event
async def on_message(msg: Message) -> None:
    if msg.author == discord_client.user:
        return

    # check if the bot is mentioned in the message
    if discord_client.user.mentioned_in(msg):
        username: str = str(msg.author)
        user_msg: str = msg.content 
        channel: str = str(msg.channel)
                 
        logger.info(f'[{channel}] {username}: "{user_msg}"')
        await send_msg(msg, user_msg)

def main() -> None:
    discord_client.run(token=DISCORD_TOK)

if __name__ == '__main__':
    main()
