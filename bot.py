import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import re

from openai import AsyncOpenAI

from AIAPI import AIAPI
from DiscordAPI import DiscordAPI
from Summarizer import Summarizer
# from OpenAIAPI import OpenAIAPI
from utils import parse_duration


ai_client: AIAPI = None
bot: commands.Bot = None


def main():
    global ai_client, bot
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

    # --- AI Configuration ---
    ai_client = AIAPI(OPENROUTER_API_KEY)

    # --- Discord Bot Configuration ---
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.members = True  # Required for nicknames

    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.run(DISCORD_TOKEN)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        # Sync slash commands with Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.tree.command(name="summarize", description="Summarizes the conversation in the current thread or channel.")
async def summarize(interaction: discord.Interaction):
    summarizer = Summarizer(ai_client)
    discord_api = DiscordAPI(interaction)

    await discord_api.think()

    try:
        # Fetch message history
        messages = await discord_api.get_messages()
        
        if not messages:
            await discord_api.followup("No messages found in this thread to summarize.")
            return

        summary = await summarizer.get_summary(messages)
        await interaction.followup.send(summary)

    except Exception as e:
        print(f"Error summarizing thread: {e}")
        await discord_api.followup(f"An error occurred while trying to summarize. Error: {str(e)}")

@bot.tree.command(name="summarize-period", description="Summarizes messages within a time period (e.g., 2h, 1d).")
async def summarize_channel(interaction: discord.Interaction, duration: str):
    summarizer = Summarizer(ai_client)
    discord_api = DiscordAPI(interaction)
    
    delta = parse_duration(duration)
    if not delta:
        await discord_api.send_message(
            f"Invalid time period: '{duration}'.\n"
            "Please use a valid number followed by a unit.\n"
            "**Supported units:**\n"
            "• `m` for minutes\n"
            "• `h` for hours\n"
            "• `d` for days\n"
            "• `w` for weeks\n"
            "• `mo` for months (30 days)\n\n"
            "**Examples:** `30m`, `12h`, `1d`, `2w`, `1mo`.",
            ephemeral=True
        )
        return

    await discord_api.think()

    try:
        cutoff_time = datetime.now(timezone.utc) - delta
        
        messages = await discord_api.get_messages(after=cutoff_time)

        if not messages:
            await discord_api.followup(f"No messages found in the last {duration}.")
            return

        summary = await summarizer.get_summary(messages)
        await discord_api.followup(summary)


    except Exception as e:
        print(f"Error summarizing channel: {e}")
        await discord_api.followup(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()