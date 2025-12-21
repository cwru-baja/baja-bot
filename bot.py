import os
import discord
from discord.ext import commands
from openai import AsyncOpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import re

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# --- Validation Checks ---
print(f"Current working directory: {os.getcwd()}")
print(f"DISCORD_TOKEN loaded: {bool(DISCORD_TOKEN)}")
if OPENROUTER_API_KEY:
    print(f"OPENROUTER_API_KEY loaded: Yes (Starts with {OPENROUTER_API_KEY[:4]}...)")
else:
    print("OPENROUTER_API_KEY loaded: No")

if not DISCORD_TOKEN or not OPENROUTER_API_KEY:
    print("Error: DISCORD_TOKEN or OPENROUTER_API_KEY not found in .env file.")
    exit(1)

# --- OpenAI Configuration ---
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://discord.com",
        "X-Title": "Discord Thread Summarizer",
    }
)

# --- Discord Bot Configuration ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True  # Required for nicknames

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        # Sync slash commands with Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def generate_summary(user_content: list) -> str:
    """Helper function to call LLM for summarization with strict rules."""
    
    # UPDATED: Focus on synthesis, grouping, and ignoring noise.
    system_instruction = (
        "You are a concise executive assistant summarizing a Discord conversation. "
        "Your goal is to provide a high-level overview, not a play-by-play transcript.\n\n"
        "Input: A transcript of text and attached images.\n"
        "Task: Create a bulleted summary of the key topics discussed.\n\n"
        "GUIDELINES:\n"
        "1. IGNORE NOISE: completely ignore keyboard smashing (e.g., 'asdfjkl'), one-word reactions, and off-topic banter that leads nowhere.\n"
        "2. GROUP TOPICS: Do not list messages chronologically. Group thoughts by topic (e.g., 'The group discussed the Aero Gas class requirements...').\n"
        "3. SYNTHESIZE OPINIONS: Instead of 'User A liked it, User B liked it', say 'The group was generally excited about X'.\n"
        "4. IMAGES: Integrate image descriptions into the context of the conversation (e.g., 'User shared a photo of a steak while discussing dinner') rather than listing them separately at the end.\n"
        "5. BREVITY: Keep the summary under 150 words unless the transcript is massive.\n"
        "6. FORMAT: Use bullet points for distinct topics."
    )

    messages_payload = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content}
    ]

    try:
        # Try primary robust model (Gemini 2.0 Flash)
        completion = await client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages_payload
        )
    except Exception as e:
        print(f"Primary model failed: {e}. Falling back to auto...")
        completion = await client.chat.completions.create(
            model="openrouter/auto",
            messages=messages_payload
        )
    
    return completion.choices[0].message.content

def parse_duration(duration_str: str) -> timedelta:
    """Parses a duration string (e.g., '1h', '30m', '2d') into a timedelta."""
    match = re.match(r"(\d+)([mhdwd])", duration_str.lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)
    elif unit == 'w':
        return timedelta(weeks=amount)
    return None

def build_transcript_with_images(messages: list) -> list:
    """
    Constructs the user content payload for the LLM, interleaving text and images.
    Includes logic to deduplicate images (original vs thumbnail).
    """
    user_content = []
    current_text_block = ""
    
    # Track seen image URLs to prevent duplicate "thumbnails" from being sent
    seen_images = set()

    for msg in messages:
        if msg.author.bot:
            continue

        # Format timestamp and author (Using Nickname/Display Name)
        timestamp = msg.created_at.strftime("%H:%M")
        msg_header = f"[{timestamp}] {msg.author.display_name}: "

        # Append text content if present
        if msg.content:
            current_text_block += f"{msg_header}{msg.content}\n"
        
        # Check for images and deduplicate
        images = []
        for att in msg.attachments:
            if att.content_type and att.content_type.startswith('image/'):
                # Check if we've already processed this URL (or a proxy of it)
                if att.url not in seen_images:
                    images.append(att)
                    seen_images.add(att.url)

        # Add image counter to help LLM understand there's only one image
        if images:
            # Add image count to text if message had no text content
            if not msg.content:
                current_text_block += f"{msg_header}[Attached {len(images)} image(s)]\n"
            else:
                # If there was text content, append the image count
                current_text_block += f"[Attached {len(images)} image(s)]\n"
            
            # Flush accumulated text before adding images
            if current_text_block:
                user_content.append({"type": "text", "text": current_text_block})
                current_text_block = ""
            
            # Add images
            for img in images:
                user_content.append({
                    "type": "image_url", 
                    "image_url": {"url": img.url}
                })

    # Flush any remaining text after the loop
    if current_text_block:
        user_content.append({"type": "text", "text": current_text_block})

    return user_content

@bot.tree.command(name="summarize-thread", description="Summarizes the conversation in the current thread.")
async def summarize_thread(interaction: discord.Interaction):
    
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("This command can only be used inside a thread.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        # Fetch message history (limit to last 100 messages)
        messages = [message async for message in interaction.channel.history(limit=100, oldest_first=True)]
        
        if not messages:
            await interaction.followup.send("No messages found in this thread to summarize.")
            return

        # Prepare content (Text + Images)
        transcript_content = build_transcript_with_images(messages)

        if not transcript_content:
            await interaction.followup.send("Not enough content to summarize.")
            return

        summary = await generate_summary(transcript_content)
        
        if summary:
            if len(summary) > 2000:
                summary = summary[:1997] + "..."
            await interaction.followup.send(f"**Thread Summary:**\n{summary}")
        else:
            await interaction.followup.send("Failed to generate a summary.")

    except Exception as e:
        print(f"Error summarizing thread: {e}")
        await interaction.followup.send(f"An error occurred while trying to summarize. Error: {str(e)}")

@bot.tree.command(name="summarize-period", description="Summarizes channel messages within a time period (e.g., 2h, 1d).")
async def summarize_channel(interaction: discord.Interaction, duration: str):
    
    delta = parse_duration(duration)
    if not delta:
        await interaction.response.send_message("Invalid duration format. Use format like '1h', '30m', '2d'.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        cutoff_time = datetime.now(timezone.utc) - delta
        
        # Limit set to 500 to prevent overload
        messages = [message async for message in interaction.channel.history(after=cutoff_time, limit=500, oldest_first=True)]

        if not messages:
            await interaction.followup.send(f"No messages found in the last {duration}.")
            return

        # Prepare content (Text + Images)
        transcript_content = build_transcript_with_images(messages)

        if not transcript_content:
            await interaction.followup.send(f"Not enough content to summarize in the last {duration}.")
            return

        summary = await generate_summary(transcript_content)

        if summary:
            if len(summary) > 2000:
                summary = summary[:1997] + "..."
            await interaction.followup.send(f"**Channel Summary ({duration}):**\n{summary}")
        else:
            await interaction.followup.send("Failed to generate a summary.")

    except Exception as e:
        print(f"Error summarizing channel: {e}")
        await interaction.followup.send(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)