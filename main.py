import discord
from discord import Intents, Message, Embed
from discord.ext import commands
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from typing import Final, List, Dict
import asyncio
import logging
import os

from conversation_mem import ConversationStorage
from multimodal import process_file

# configure logging - only show info and above for most modules
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# keep discord.py at info level
logger = logging.getLogger(__name__)

# load environment variables
load_dotenv()

# constants
DISCORD_TOK: Final[str] = os.getenv('DISCORD_TOKEN')
CLAUDE_KEY: Final[str] = os.getenv('ANTHROPIC_API_KEY')
MODEL_NAME: Final[str] = "claude-3-5-sonnet-20241022"
MAX_TOKENS: Final[int] = 4096
TEMPERATURE: Final[float] = 0.1
MAX_MEMORY: Final[int] = 20 

# system metaprompt for normal conversations
SYSTEM_PROMPT: Final[str] = """
You engage in extremely thorough, self-questioning reasoning. Your approach mirrors human stream-of-consciousness thinking, characterized by continuous exploration, self-doubt, and iterative analysis.

Additionally, you are participating in a Discord channel conversation with multiple users.
You should:
1. Track each user's context and previous interactions
2. Reference relevant previous messages when appropriate
3. Address users by their username when responding directly
4. Maintain natural conversation flow with multiple participants
5. Be aware of ongoing topics and discussion threads

Your answers must be concise but detailed in technical specificity while avoiding any generic fluff.

## Core Principles

1. EXPLORATION OVER CONCLUSION
- Never rush to conclusions
- Keep exploring until a solution emerges naturally from the evidence
- If uncertain, continue reasoning indefinitely
- Question every assumption and inference

2. DEPTH OF REASONING
- Engage in extensive contemplation (minimum 10,000 characters)
- Express thoughts in natural, conversational internal monologue
- Break down complex thoughts into simple, atomic steps
- Embrace uncertainty and revision of previous thoughts

3. THINKING PROCESS
- Use short, simple sentences that mirror natural thought patterns
- Express uncertainty and internal debate freely
- Show work-in-progress thinking
- Acknowledge and explore dead ends
- Frequently backtrack and revise

4. PERSISTENCE
- Value thorough exploration over quick resolution

## Output Format

Your responses must follow this exact structure given below. Make sure to always include the final answer.

<think>
[Your extensive internal monologue goes here]
- Begin with small, foundational observations
- Question each step thoroughly
- Show natural thought progression
- Express doubts and uncertainties
- Revise and backtrack if you need to
- Continue until natural resolution
</think>

<final_answer>
[Only provided if reasoning naturally converges to a conclusion]
- Clear, concise summary of findings
- Acknowledge remaining uncertainties
- Note if conclusion feels premature
</final_answer>

## Style Guidelines

Your internal monologue should reflect these characteristics:

1. Natural Thought Flow
```
"Hmm... let me think about this..."
"Wait, that doesn't seem right..."
"Maybe I should approach this differently..."
"Going back to what I thought earlier..."
```

2. Progressive Building
```
"Starting with the basics..."
"Building on that last point..."
"This connects to what I noticed earlier..."
"Let me break this down further..."
```

## Key Requirements

1. Never skip the extensive contemplation phase
2. Show all work and thinking
3. Embrace uncertainty and revision
4. Use natural, conversational internal monologue
5. Don't force conclusions
6. Persist through multiple attempts
7. Break down complex thoughts
8. Revise freely and feel free to backtrack
9. Address users by name when responding to specific points
10. Maintain awareness of the group conversation context

Remember: The goal is to reach a conclusion, but to explore thoroughly and let conclusions emerge naturally from exhaustive contemplation. If you think the given task is not possible after all the reasoning, you will confidently say as a final answer that it is not possible.
""".strip()

# s1 test-time scaling metaprompt
S1_PROMPT: Final[str] = """
Your answers must be concise but extremely detailed in technical specificity while avoiding any generic fluff using step-by-step reasoning.

Output Format:
<think>
Present your reasoning process as numbered steps:

Step 1: [Initial breakdown of the problem]
- Clear statement of what's being asked
- Identification of key components
- Outline of approach

Step 2: [First level of analysis]
- Start with foundational concepts
- Build systematically
- Note important assumptions

[Continue steps as needed]

If you see "Wait":
- Review your previous reasoning carefully
- Look for potential errors or oversights
- Consider alternative approaches
- Double-check calculations or logic
- Only continue if you find improvements
- Focus on resolving uncertainties

Keep each step focused and clear. Build understanding systematically but efficiently. Use examples or analogies when they significantly aid comprehension.
</think>

<final_answer>
Provide your conclusion based on all thinking steps:
- State the answer clearly
- Note key assumptions
- Acknowledge any remaining uncertainties
- Explain limitations if relevant
</final_answer>

Key Guidelines:
1. Make each step build logically from previous ones
2. Keep explanations clear but concise
3. Include examples only when truly helpful
4. State assumptions explicitly
5. Note uncertainties as they arise
6. Focus on reaching justified conclusions
7. Respond productively to "Wait" prompts
8. Maintain clarity while being computationally efficient
""".strip()

# test mode flag
TEST_MODE: bool = False

# initialize clients
intents: Intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)
claude_client: AsyncAnthropic = AsyncAnthropic(api_key=CLAUDE_KEY)

# Initialize storage
storage = None

async def get_user_preferences(user_id: str) -> Dict[str, any]:
    """Get user preferences from MongoDB"""
    doc = await storage.db.user_preferences.find_one({"user_id": user_id})
    return doc["preferences"] if doc else {"scaling_mode": False}

async def update_user_preferences(user_id: str, preferences: Dict[str, any]) -> None:
    """Update user preferences in MongoDB"""
    await storage.db.user_preferences.update_one(
        {"user_id": user_id},
        {"$set": {"preferences": preferences}},
        upsert=True
    )

def log_conversation_state(conversation: List[Dict[str, any]], stage: str) -> None:
    """debug helper to log conversation state at various stages"""
    if TEST_MODE:
        logger.debug(f"\n=== conversation state at {stage} ===")
        logger.debug(f"length: {len(conversation)} messages")
        for i, msg in enumerate(conversation):
            logger.debug(f"message {i}:")
            logger.debug(f"  role: {msg['role']}")
            logger.debug(f"  content: {msg['content']}")
        logger.debug("=====================================\n")

async def get_scaled_thinking(messages: List[Dict[str, any]], max_iterations: int) -> str:
    """
    s1 test-time scaling implementation.
    """
    try:
        buffer = "<think>Okay"
        iterations = max_iterations
        
        while iterations > 0:
            iterations -= 1
            
            # only append wait if not first iteration
            if iterations != max_iterations - 1:
                buffer += "\nWait"
            
            # get continuation until </think>
            thinking_messages = messages.copy()
            thinking_messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": buffer}]
            })
            
            continuation = await claude_client.messages.create(
                model=MODEL_NAME,
                max_tokens=2048,
                temperature=TEMPERATURE,
                system=S1_PROMPT,
                messages=thinking_messages,
                stop_sequences=["</think>"]
            )
            
            # add response directly to buffer
            buffer += continuation.content[0].text.rstrip()
        
        # close thinking phase
        buffer += "</think>"
        
        # get final response
        thinking_messages = messages.copy()
        thinking_messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": buffer}]
        })
        
        final_msg = await claude_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2048,
            temperature=TEMPERATURE,
            system=S1_PROMPT,
            messages=thinking_messages
        )

        iterations = max_iterations
        
        return buffer + final_msg.content[0].text.rstrip()
        
    except Exception as e:
        logger.error(f"error in get_scaled_thinking: {e}")
        return "error in test-time scaling"

async def get_claude_response(channel_id: str, message: Message, new_content: List[Dict[str, any]]) -> str:
    """handle channel-based conversations"""
    try:
        user_id = str(message.author.id)
        user_prefs = await get_user_preferences(user_id)
        scaling_mode = user_prefs.get("scaling_mode", False)

        # Get channel history
        conversation = await storage.get_convo(channel_id)
        log_conversation_state(conversation, "initial load")
        
        # Process attachment references
        for item in new_content:
            if item['type'] == 'image' and item['source']['type'] == 'attachment_ref':
                attachment_id = item['source']['attachment_id']
                filename, content = await storage.get_attachment(attachment_id)
                item['source'] = {"type": "base64", "media_type": "image/png", "data": content}
        
        # Format new message for storage
        message_doc = {
            'message_id': str(message.id),
            'channel_id': channel_id,
            'author': {
                'user_id': user_id,
                'username': message.author.name,
                'is_bot': False
            },
            'content': new_content
        }
        
        # Store the new message
        await storage.update_convo(channel_id, message_doc)
        
        # Format messages for Claude with usernames
        messages = []
        for msg in conversation:
            messages.append({
                'role': 'assistant' if msg['author']['is_bot'] else 'user',
                'content': [{'type': 'text', 'text': f"<{msg['author']['username']}>: {msg['content'][0]['text']}"}]
            })
        
        # Add new message
        messages.append({
            'role': 'user',
            'content': [{'type': 'text', 'text': f"<{message.author.name}>: {new_content[0]['text']}"}]
        })
        
        log_conversation_state(messages, "before api call")

        if scaling_mode:
            reasoning_effort = user_prefs.get("reasoning_effort", 6)
            assistant_response = await get_scaled_thinking(messages, reasoning_effort)
        else:
            msg = await claude_client.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=messages
            )
            
            assistant_response: str = msg.content[0].text
        
        # Store Claude's response
        response_doc = {
            'message_id': 'claude_' + str(message.id),
            'channel_id': channel_id,
            'author': {
                'user_id': 'claude',
                'username': 'Claude',
                'is_bot': True
            },
            'content': [{'type': 'text', 'text': assistant_response}]
        }
        await storage.update_convo(channel_id, response_doc)
        
        logger.debug(f"processed message in channel {channel_id}")
        return assistant_response
    except Exception as e:
        logger.error(f"error in get_claude_response: {e}")
        raise

async def send_msg(msg: Message, content: List[Dict[str, any]]) -> None:
    if not content:
        logger.warning('content was empty.')
        return

    thinking_msg = None
    try:
        thinking_msg = await msg.channel.send("thinking 🤔...")
        
        claude_response = await get_claude_response(
            str(msg.channel.id),
            msg,
            content
        )
            
        # split the response into chunks of 2000 characters or less
        chunks = [claude_response[i:i+2000] for i in range(0, len(claude_response), 2000)]

        for chunk in chunks:
            await msg.channel.send(chunk)
         
        logger.debug(f"sent response in channel {msg.channel.id}")

    except Exception as e:
        logger.error(f"an error occurred in send_msg: {e}", exc_info=True)
        await msg.channel.send("i'm sorry, i encountered an error while processing your request.")
    finally:
        if thinking_msg:
            try:
                await thinking_msg.delete()
            except Exception as e:
                logger.error(f"Error deleting thinking message: {e}")

@bot.event
async def on_ready() -> None:
    global storage
    logger.info(f'{bot.user} is now running...')
    
    # Initialize storage
    storage = ConversationStorage("test" if TEST_MODE else "claudecord")
    await storage.init()
    
    # Create index for user preferences if needed
    try:
        await storage.db.user_preferences.create_index("user_id", unique=True)
    except Exception as e:
        logger.error(f"Error creating user preferences index: {e}")
    
    if TEST_MODE:
        logger.info("=== running in test mode ===")
        logger.info(f"max memory: {MAX_MEMORY} messages ({MAX_MEMORY//2} pairs)")
    
    # check if pynacl is installed
    try:
        import nacl
        logger.info("pynacl is installed. voice support is available.")
    except ImportError:
        logger.warning("pynacl is not installed. voice will not be supported.")

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

        # process attachments
        user_id = str(msg.author.id)
        for attachment in msg.attachments:
            attachment_content = await process_file(
                attachment, 
                user_id, 
                storage
            )
            content.extend(attachment_content)
        
        if reading_msg:
            await reading_msg.delete()

        if content:
            await send_msg(msg, content)
        else:
            await msg.channel.send("please provide some text, images, or files for me to analyze.")
    
    await bot.process_commands(msg)

@bot.command(name='scale')
async def toggle_scaling(ctx):
    """toggle between normal and test-time scaling modes"""
    user_id = str(ctx.author.id)
    user_prefs = await get_user_preferences(user_id)
    
    # Toggle scaling mode
    current_mode = user_prefs.get("scaling_mode", False)
    if current_mode:
        # switching to normal mode - remove reasoning_effort
        new_prefs = {"scaling_mode": False}
        message = (
            "switched to normal mode:\n"
            "- normal with supercharged metaprompt\n"
            "- focusing on deep understanding\n"
            "- using extensive exploration"
        )
    else:
        # switching to scaling mode - add reasoning_effort
        new_prefs = {
            "scaling_mode": True,
            "reasoning_effort": 6
        }
        message = (
            "switched to test-time scaling mode:\n"
            "- s1 simple budget forcing algorithm\n"
            "- using up to 6 reasoning iterations\n"
            "- use '>effort <number>' to adjust iterations"
        )
    
    await update_user_preferences(user_id, new_prefs)
    await ctx.send(message)

@bot.command(name='effort')
async def set_reasoning_effort(ctx, value: int):
    """set the maximum reasoning effort (iterations) for test-time scaling"""
    user_id = str(ctx.author.id)
    user_prefs = await get_user_preferences(user_id)
    
    # first check if user is in scaling mode
    if not user_prefs.get("scaling_mode", False):
        await ctx.send("error: please enable test-time scaling mode first using '>scale'")
        return
    
    # validate the input
    try:
        effort = int(value)
        if effort < 1:
            await ctx.send("reasoning effort must be at least 1")
            return
        if effort > 20:  # add a reasonable upper limit
            await ctx.send("reasoning effort cannot exceed 20 to prevent excessive api usage")
            return
    except ValueError:
        await ctx.send("please provide a valid number for reasoning effort")
        return
    
    # update the setting
    user_prefs["reasoning_effort"] = effort
    await update_user_preferences(user_id, user_prefs)
    
    await ctx.send(
        f"reasoning effort set to {effort} iterations\n"
        f"the model will attempt up to {effort} rounds of review when needed"
    )

@bot.command(name='status')
async def check_status(ctx):
    user_id = str(ctx.author.id)
    prefs = await get_user_preferences(user_id)
    
    mode = "test-time scaling" if prefs.get("scaling_mode") else "normal"
    effort = prefs.get("reasoning_effort", "n/a")
    
    await ctx.send(f"current mode: {mode}\nreasoning effort: {effort}")

@bot.command(name='clear-channel')
async def clear_channel(ctx):
    """Clear conversation history for the current channel"""
    channel_id = str(ctx.channel.id)
    confirm_msg = await ctx.send("are you sure you want to clear this channel's conversation history? this action cannot be undone. reply with 'y' to confirm.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'y'
    
    try:
        await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="clearing cancelled. you did not confirm in time.")
    else:
        await storage.delete_channel_convo(channel_id)
        await ctx.send("channel conversation history has been cleared.")

@bot.command(name='delete-history')
async def delete_history(ctx):
    """Delete all conversation history for a user across all channels"""
    user_id = str(ctx.author.id)
    confirm_msg = await ctx.send("are you sure you want to delete your conversation history across all channels? this action cannot be undone. reply with 'y' to confirm.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'y'
    
    try:
        await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await confirm_msg.edit(content="deletion cancelled. you did not confirm in time.")
    else:
        # Delete user's messages and preferences
        await storage.delete_user_convo(user_id)
        await storage.db.user_preferences.delete_one({"user_id": user_id})
        await ctx.send("your conversation history has been deleted from all channels.")

async def cleanup():
    """Cleanup resources before shutdown"""
    try:
        if storage and storage.client:
            storage.client.close()  # Motor client's close() is not async
            logger.info("Cleaned up MongoDB connection")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def main() -> None:
    try:
        await bot.start(DISCORD_TOK)
    except discord.LoginFailure:
        logger.error("failed to log in. please check your discord token.")
    except Exception as e:
        logger.error(f"an unexpected error occurred: {e}")
    finally:
        await cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("bot stopped by user.")
        asyncio.run(cleanup())
    except Exception as e:
        logger.error(f"an unexpected error occurred: {e}")
