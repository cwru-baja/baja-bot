import io
import logging
import os
import sys
from datetime import datetime, timezone

import aiohttp
import discord
from discord import ButtonStyle, File, SelectOption
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv

from AIAPI import AIAPI
from DiscordAPI import DiscordAPI
from Notion.NotionAPI import NotionAPI
from Notion.Page import Page
from Summarizer import Summarizer
# from OpenAIAPI import OpenAIAPI
from utils import parse_duration, make_embed_from_part, make_part_title

messages_before_rename = 3

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


@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself to prevent infinite loops
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.Thread):

        # print(message.channel.id in threads)
        # if message.channel.id in threads:
        #     print(threads[message.channel.id])
        # Optional: Check for specific content, e.g., a command or keyword
        # if "hello bot" in message.content.lower():
            # Send a reply directly to the thread
        if not message.channel.starter_message:
            return

        if message.channel.starter_message.content == message.channel.name:
            print("LETS GO RENAMIN!")
            discord_api = DiscordAPI(message)
            summarizer = Summarizer(ai_client)
            messages = await discord_api.get_messages(limit=messages_before_rename+5)
            if len(messages) == messages_before_rename:
                new_title = await summarizer.get_title(messages)
                if new_title:
                    await message.channel.edit(name=new_title)

    await bot.process_commands(message)


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


async def get_part_drawing(part: Page) -> File | None:
    # fd, path = tempfile.mkstemp()
    # os.close(fd)

    file_prop = part.get_property("Drawing (PDF)/DXF")
    if not file_prop:
        return None
    url = file_prop.value[0]["file"]["url"]
    file_name = file_prop.value[0]["name"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()

                data = await resp.read()  # read all content into memory
                file_buffer = io.BytesIO(data)  # create an in-memory file
                file_buffer.seek(0)  # make sure we're at the start

                return discord.File(file_buffer, file_name)
    except Exception as e:
        return None
        # await interaction.response.send_message(
        #     file=discord.File(file_buffer, filename=file_name)
        # )
        # await interaction.response.send_message(file=discord.File(tmp, filename=file_name))
    #
    # finally:
    #     # Always delete the local file
    #     if os.path.exists(path):
    #         os.remove(path)


def make_part_callback(part: Page):
    embed = make_embed_from_part(part)

    async def callback(interaction: discord.Interaction):
        view = await get_part_update_view(part)
        file = await get_part_drawing(part)
        await interaction.response.send_message(embed=embed, files=[file] if file else [], view=view)

    return callback


async def get_part_update_view(part: Page) -> View:
    part_name = make_part_title(part)
    prop_schema = await notion_client.retrieve_data(PARTS_DATA_SOURCE_ID)
    view = View()
    design_schema = prop_schema.get_property("Design Status").value["options"]
    design_status = part.get_property("Design Status").value["name"]

    design_options = [SelectOption(label=f"Design status - {option["name"]}", value=option["name"],
                                   default=option["name"] == design_status) for option in design_schema]
    design_selector = Select(
        max_values=1,
        placeholder="Design Status",
        options=design_options
    )

    async def design_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        selected = interaction.data["values"][0]
        logging.info(f"Updated design status for \"{part_name}\" to \"{selected}\"")
        # print(interaction.data["values"])
        await part.update(part.get_property("Design Status"), {
            "status": {
                "name": selected
            }
        })
        await interaction.followup.send(f"Updated design status for \"{part_name}\" to \"{selected}\"")

    design_selector.callback = design_callback
    # selector.callback = lambda interaction: print(interaction.data["values"])
    view.add_item(design_selector)

    po_schema = prop_schema.get_property("PO Status").value["options"]
    po_status = part.get_property("PO Status").value["name"]

    po_options = [SelectOption(label=f"PO status - {option["name"]}", value=option["name"],
                               default=option["name"] == po_status) for option in po_schema]
    po_selector = Select(
        max_values=1,
        placeholder="Mfg Status",
        options=po_options
    )

    async def po_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        selected = interaction.data["values"][0]
        logging.info(f"Updated po status for \"{part_name}\" to \"{selected}\"")
        # print(interaction.data["values"])
        await part.update(part.get_property("PO Status"), {
            "status": {
                "name": selected
            }
        })
        await interaction.followup.send(f"Updated po status for \"{part_name}\" to \"{selected}\"")

    po_selector.callback = po_callback
    # selector.callback = lambda interaction: print(interaction.data["values"])
    view.add_item(po_selector)

    mfg_schema = prop_schema.get_property("Mfg Status").value["options"]
    mfg_status = part.get_property("Mfg Status").value["name"]

    mfg_options = [SelectOption(label=f"Mfg status - {option["name"]}", value=option["name"],
                                default=option["name"] == mfg_status) for option in mfg_schema]
    mfg_selector = Select(
        max_values=1,
        placeholder="Mfg Status",
        options=mfg_options
    )

    async def mfg_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        selected = interaction.data["values"][0]
        logging.info(f"Updated mfg status for \"{part_name}\" to \"{selected}\"")
        # print(interaction.data["values"])
        await part.update(part.get_property("Mfg Status"), {
            "status": {
                "name": selected
            }
        })
        await interaction.followup.send(f"Updated mfg status for \"{part_name}\" to \"{selected}\"")

    mfg_selector.callback = mfg_callback
    # selector.callback = lambda interaction: print(interaction.data["values"])
    view.add_item(mfg_selector)

    make_button = Button(style=ButtonStyle.primary, label="Make Part")
    parts_made_prop = part.get_property("Qty Made")

    async def part_made_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        await part.refetch_page()
        if not parts_made_prop:
            new_parts = 1
        else:
            new_parts = parts_made_prop.value + 1
        await part.update(parts_made_prop, {
            "number": new_parts
        })
        await interaction.followup.send(f"Updated Qty Made for \"{part_name}\" to {new_parts}")
    make_button.callback = part_made_callback
    view.add_item(make_button)

    return view


@bot.tree.command(name="get-part", description="Gets information about a specified part from notion.")
async def get_part(interaction: discord.Interaction, search_term: str):
    # await get_part_update_view(None)
    # return
    logger.info(f"Part request: by \"{interaction.user.name}\" for \"{search_term}\"")
    discord_api = DiscordAPI(interaction)

    await discord_api.think()
    try:

        filter_object = {
            "or": [
                {
                    "property": "Part Number",
                    "rich_text": {
                        "contains": search_term
                    }
                },
                {
                    "property": "Part Name",
                    "title": {
                        "contains": search_term
                    }
                }
            ]}

        sort_object = [
            {
                "timestamp": "last_edited_time",
                "direction": "descending"
            }
        ]

        base_result = await notion_client.query_data(PARTS_DATA_SOURCE_ID, filter=filter_object, sorts=sort_object)
        search_results = base_result.results
        has_more = base_result.has_more
        if not len(search_results):
            await discord_api.followup(f"No results found for part '{search_term}'.")
            return None

        max_parts = 5
        filtered_search_results = search_results[:max_parts]
        did_truncate = len(search_results) > max_parts or has_more
        # embeds = [generate_embed_from_part(part) for part in filtered_search_results]

        if len(filtered_search_results) > 1:
            view = await get_part_search_select_view(filtered_search_results)

            part_titles = [
                make_part_title(part) for part in filtered_search_results]
            message = \
                (f"Search results for: \"{search_term}\" {"(truncated)" if did_truncate else ""}:\n"
                 "Click button for more info.\n"
                 f"{"\n".join(f"{i}. {part_titles[i]}" for i, _ in enumerate(filtered_search_results))}")
            await discord_api.followup(message, view=view)
        else:
            view = await get_part_update_view(filtered_search_results[0])
            file = await get_part_drawing(filtered_search_results[0])
            await discord_api.followup("", embed=make_embed_from_part(filtered_search_results[0]),
                                       files=[file] if file else [],
                                       view=view)
    except Exception as e:
        logger.warning(f"Error getting part: {e}")
        await discord_api.followup(f"An error occurred: {str(e)}")
        raise e

    return None


async def get_part_search_select_view(filtered_search_results):
    view = View(timeout=60)
    for i, result in enumerate(filtered_search_results):
        button = Button(
            label=str(i + 1),
            style=ButtonStyle.secondary,
        )

        # part_embed = make_embed_from_part(result)
        callback = make_part_callback(result)

        button.callback = callback
        view.add_item(button)
    return view


bot.run(discord_token)
