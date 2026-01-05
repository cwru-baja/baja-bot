import os
import sys

import discord
import webcolors
from discord import ButtonStyle
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv
from datetime import datetime, timezone

from AIAPI import AIAPI
from DiscordAPI import DiscordAPI
from LogFormatter import LogFormatter
from Notion.NotionAPI import NotionAPI
from Notion.Page import Page
from Summarizer import Summarizer
# from OpenAIAPI import OpenAIAPI
from utils import parse_duration

import logging

ai_client: AIAPI = None
bot: commands.Bot = None
notion_client: NotionAPI = None

PARTS_DATA_SOURCE_ID = "22d471ee-8bfe-8135-855c-000bba8ef8cc"

# Load environment variables
load_dotenv()

discord_token = os.getenv('DISCORD_TOKEN')
openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
notion_token = os.getenv('NOTION_TOKEN')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# logger = logging.getLogger()
#
# ch = logging.StreamHandler()
# ch.setStream(sys.stdout)
# ch.setLevel(logging.DEBUG)
#
# ch.setFormatter(LogFormatter())
#
# logger.addHandler(ch)

# --- Validation Checks ---
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"DISCORD_TOKEN loaded: {bool(discord_token)}")
logger.info(f"NOTION_TOKEN loaded: {bool(notion_token)}")
if openrouter_api_key:
    logger.info(f"OPENROUTER_API_KEY loaded: Yes (Starts with {openrouter_api_key[:4]}...)")
else:
    logger.warning("OPENROUTER_API_KEY loaded: No")

if not discord_token or not openrouter_api_key or not notion_token:
    logger.error("Error: token not found in .env file.")
    exit(1)

# --- AI Configuration ---
ai_client = AIAPI(openrouter_api_key)

notion_client = NotionAPI(notion_token)

# --- Discord Bot Configuration ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True  # Required for nicknames

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    try:
        # Sync slash commands with Discord
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


@bot.tree.command(name="summarize", description="Summarizes the conversation in the current thread or channel.")
async def summarize(interaction: discord.Interaction):
    logger.info(f"Summarize: by \"{interaction.user.name}\" in \"{interaction.channel.name}\"")
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
        logger.warning(f"Error summarizing thread: {e}")
        await discord_api.followup(f"An error occurred while trying to summarize. Error: {str(e)}")


@bot.tree.command(name="summarize-period", description="Summarizes messages within a time period (e.g., 2h, 1d).")
async def summarize_period(interaction: discord.Interaction, duration: str):
    logger.info(
        f"Summarize-period: by \"{interaction.user.name}\" in \"{interaction.channel.name}\" for \"{duration}\"")

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
        logger.warning(f"Error summarizing channel: {e}")
        await discord_api.followup(f"An error occurred: {str(e)}")


def make_part_callback(embed: discord.Embed):
    async def callback(interaction: discord.Interaction):
        await interaction.response.send_message(embed=embed)

    return callback


@bot.tree.command(name="get-part", description="Gets information about a specified part from notion.")
async def get_part(interaction: discord.Interaction, part_number: str):
    logger.info(f"Part request: by \"{interaction.user.name}\" for \"{part_number}\"")
    discord_api = DiscordAPI(interaction)

    await discord_api.think()
    try:

        filter_object = {
            "property": "Part Number",
            "rich_text": {
                "contains": part_number,
            }
        }
        base_result = await notion_client.query_data(PARTS_DATA_SOURCE_ID, filter_object)
        search_results = base_result.results
        has_more = base_result.has_more
        if not len(search_results):
            await discord_api.followup(f"No results found for part number '{part_number}'.")
            return None

        max_parts = 5
        filtered_search_results = search_results[:max_parts]
        did_truncate = len(search_results) > max_parts or has_more
        # embeds = [generate_embed_from_part(part) for part in filtered_search_results]

        if len(filtered_search_results) > 1:
            view = View(timeout=60)
            for i, result in enumerate(filtered_search_results):
                button = Button(
                    label=str(i),
                    style=ButtonStyle.secondary,
                    custom_id=f"part-{i}"
                )

                part_embed = generate_embed_from_part(result)
                callback = make_part_callback(part_embed)

                button.callback = callback
                view.add_item(button)

            part_titles = [
                f"{part.get_property("Part Name").value[0]["plain_text"]}: {part.get_property("Part Number").value[0]["plain_text"]}"
                for part in filtered_search_results]
            message = \
                (f"Search results for: \"{part_number}\" {"(truncated)" if did_truncate else ""}:\n"
                 "Click button for more info.\n"
                 f"{"\n".join(f"{i}. {part_titles[i]}" for i, _ in enumerate(filtered_search_results))}")
            await discord_api.followup(message, view=view)
        else:
            await discord_api.followup("", embed=generate_embed_from_part(filtered_search_results[0]))
    except Exception as e:
        logger.warning(f"Error getting part: {e}")
        await discord_api.followup(f"An error occurred: {str(e)}")
        raise e

    return None


def generate_embed_from_part(part: Page) -> discord.Embed:
    part_family = part.get_property("Part Family")
    primary_designer = part.get_property("Primary Designer")
    part_name = part.get_property("Part Name")
    part_number = part.get_property("Part Number")

    if part_family:
        color_str = part_family.value[0]["color"]
    else:
        color_str = "gray"
    hex_color = webcolors.name_to_hex(color_str)
    if primary_designer:
        designer_name = primary_designer.value[0]["name"]
    else:
        designer_name = "No Designer Listed"

    part_title = f"{part_name.value[0]["plain_text"]}: {part_number.value[0]["plain_text"]}"
    embed = discord.Embed(
        title=part_title,
        color=discord.Color.from_str(hex_color)
    )

    design_status = part.get_property("Design Status")
    analysis_status = part.get_property("Analysis Status")
    mfg_status = part.get_property("Mfg Status")
    embed.add_field(name="Design Status", value=design_status.value["name"], inline=True)
    embed.add_field(name="Analysis Status", value=analysis_status.value["name"], inline=True)
    embed.add_field(name="Mfg Status", value=mfg_status.value["name"], inline=True)

    embed.add_field(name="Designer", value=designer_name, inline=False)

    return embed


bot.run(discord_token)
