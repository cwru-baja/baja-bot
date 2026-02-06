import io
import logging
import os
import sys
from datetime import datetime, timezone, time as dt_time

import aiohttp
import discord
from discord import ButtonStyle, File, SelectOption
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv
import pytz

from ai_api import AIAPI
from discord_api import DiscordAPI
from baja_notion.notion_api import NotionAPI
from baja_notion.page import Page
from summarizer import Summarizer
from schedule_storage import ScheduleStorage
import schedule_manager
# from OpenAIAPI import OpenAIAPI
from utils import parse_duration, make_embed_from_part, make_part_title


# Bot config values
messages_before_rename = 5

ai_client: AIAPI = None
bot: commands.Bot = None
notion_client: NotionAPI = None
schedule_storage: ScheduleStorage = None

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
    global schedule_storage
    
    logger.info(f'Logged in as {bot.user.name}')
    try:
        # Sync slash commands with Discord
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
    
    # Initialize schedule storage and load scheduled tasks
    try:
        schedule_storage = ScheduleStorage()
        logger.info("Schedule storage initialized")
        await schedule_manager.load_all_schedules(bot, schedule_storage, ai_client)
    except Exception as e:
        logger.error(f"Failed to initialize scheduled summaries: {e}")


@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself to prevent infinite loops
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.Thread):

        try:
            if not message.channel.starter_message:
                return
                
            if message.channel.starter_message.clean_content.startswith(message.channel.name):
                discord_api = DiscordAPI(message)
                summarizer = Summarizer(ai_client)
                messages = await discord_api.get_messages(limit=messages_before_rename+5)
                if len(messages) == messages_before_rename:
                    # If we are here, we are renaming

                    starter_message = message.channel.starter_message
                    # Add starter message to the list so it has something to work with
                    messages.insert(0, starter_message)
                    old_name = message.channel.name
                    new_title = await summarizer.get_title(messages)
                    if new_title:
                        await message.channel.edit(name=new_title)
                        logging.info(f"Renamed thread '{old_name}' to '{new_title}'")
        except Exception as e:
            logger.warning(f"Failed to rename thread '{message.channel.name}': {e}")

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


@bot.tree.command(name="schedule-summary", description="Schedule automatic summaries for a channel")
async def schedule_summary(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    time: str,
    interval: str,
    lookback: str,
    output_channel: discord.TextChannel
):
    """
    Schedule a recurring summary for a channel
    
    Args:
        channel: Channel to summarize
        time: Time of day (e.g., "14:00" for 2:00 PM EST)
        interval: How often to repeat (e.g., "24h", "12h", "1d")
        lookback: How far back to look (e.g., "24h", "1d")
        output_channel: Where to post summaries
    """
    logger.info(f"Schedule-summary: by '{interaction.user.name}' for #{channel.name}")
    discord_api = DiscordAPI(interaction)
    
    await discord_api.think()
    
    try:
        # Parse time string
        try:
            time_parts = time.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            start_time = dt_time(hour=hour, minute=minute)
        except (ValueError, IndexError):
            await discord_api.followup(
                f"Invalid time format: '{time}'. Please use HH:MM format (e.g., '14:00' for 2:00 PM).",
                ephemeral=True
            )
            return
        
        # Parse interval
        interval_delta = parse_duration(interval)
        if not interval_delta or interval_delta.total_seconds() < 3600:
            await discord_api.followup(
                f"Invalid interval: '{interval}'. Must be at least 1 hour (e.g., '1h', '24h', '1d').",
                ephemeral=True
            )
            return
        
        interval_hours = int(interval_delta.total_seconds() / 3600)
        
        # Validate lookback
        lookback_delta = parse_duration(lookback)
        if not lookback_delta:
            await discord_api.followup(
                f"Invalid lookback duration: '{lookback}'. Use format like '24h', '1d', '12h'.",
                ephemeral=True
            )
            return
        
        # Get guild timezone
        timezone_str = schedule_storage.get_guild_timezone(interaction.guild.id)
        
        # Save to database
        schedule_id = schedule_storage.add_schedule(
            guild_id=interaction.guild.id,
            channel_ids=[channel.id],
            target_name=channel.name,
            schedule_type='channel',
            output_channel_id=output_channel.id,
            start_time=start_time,
            interval_hours=interval_hours,
            lookback_duration=lookback,
            created_by_user_id=interaction.user.id
        )
        
        # Create and start the task
        schedule = schedule_storage.get_schedule(schedule_id)
        task = schedule_manager.create_schedule_task(schedule, bot, schedule_storage, ai_client)
        schedule_manager.start_schedule_task(schedule_id, task)
        
        await discord_api.followup(
            f"✅ Schedule created! (ID: {schedule_id})\n"
            f"• Channel: {channel.mention}\n"
            f"• Time: {time} {timezone_str}\n"
            f"• Interval: Every {interval}\n"
            f"• Lookback: {lookback}\n"
            f"• Output: {output_channel.mention}\n\n"
            f"First summary will run at the next scheduled time."
        )
        
    except Exception as e:
        logger.error(f"Error creating schedule: {e}", exc_info=True)
        await discord_api.followup(f"An error occurred: {str(e)}")


@bot.tree.command(name="schedule-category-summary", description="Schedule automatic summaries for a category")
async def schedule_category_summary(
    interaction: discord.Interaction,
    category_name: str,
    time: str,
    interval: str,
    lookback: str,
    output_channel: discord.TextChannel
):
    """
    Schedule a recurring summary for all channels in a category
    
    Args:
        category_name: Name of the category
        time: Time of day (e.g., "14:00" for 2:00 PM EST)
        interval: How often to repeat (e.g., "24h", "12h", "1d")
        lookback: How far back to look (e.g., "24h", "1d")
        output_channel: Where to post summaries
    """
    logger.info(f"Schedule-category-summary: by '{interaction.user.name}' for category '{category_name}'")
    discord_api = DiscordAPI(interaction)
    
    await discord_api.think()
    
    try:
        # Find category
        category = discord.utils.get(interaction.guild.categories, name=category_name)
        if not category:
            await discord_api.followup(
                f"Category '{category_name}' not found. Please check the spelling.",
                ephemeral=True
            )
            return
        
        # Get all text channels in category
        text_channels = category.text_channels
        if not text_channels:
            await discord_api.followup(
                f"Category '{category_name}' has no text channels.",
                ephemeral=True
            )
            return
        
        channel_ids = [ch.id for ch in text_channels]
        
        # Parse time string
        try:
            time_parts = time.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            start_time = dt_time(hour=hour, minute=minute)
        except (ValueError, IndexError):
            await discord_api.followup(
                f"Invalid time format: '{time}'. Please use HH:MM format (e.g., '14:00' for 2:00 PM).",
                ephemeral=True
            )
            return
        
        # Parse interval
        interval_delta = parse_duration(interval)
        if not interval_delta or interval_delta.total_seconds() < 3600:
            await discord_api.followup(
                f"Invalid interval: '{interval}'. Must be at least 1 hour (e.g., '1h', '24h', '1d').",
                ephemeral=True
            )
            return
        
        interval_hours = int(interval_delta.total_seconds() / 3600)
        
        # Validate lookback
        lookback_delta = parse_duration(lookback)
        if not lookback_delta:
            await discord_api.followup(
                f"Invalid lookback duration: '{lookback}'. Use format like '24h', '1d', '12h'.",
                ephemeral=True
            )
            return
        
        # Get guild timezone
        timezone_str = schedule_storage.get_guild_timezone(interaction.guild.id)
        
        # Save to database
        schedule_id = schedule_storage.add_schedule(
            guild_id=interaction.guild.id,
            channel_ids=channel_ids,
            target_name=category_name,
            schedule_type='category',
            output_channel_id=output_channel.id,
            start_time=start_time,
            interval_hours=interval_hours,
            lookback_duration=lookback,
            created_by_user_id=interaction.user.id
        )
        
        # Create and start the task
        schedule = schedule_storage.get_schedule(schedule_id)
        task = schedule_manager.create_schedule_task(schedule, bot, schedule_storage, ai_client)
        schedule_manager.start_schedule_task(schedule_id, task)
        
        channel_list = ", ".join([f"#{ch.name}" for ch in text_channels])
        
        await discord_api.followup(
            f"✅ Category schedule created! (ID: {schedule_id})\n"
            f"• Category: {category_name} ({len(text_channels)} channels)\n"
            f"• Channels: {channel_list}\n"
            f"• Time: {time} {timezone_str}\n"
            f"• Interval: Every {interval}\n"
            f"• Lookback: {lookback}\n"
            f"• Output: {output_channel.mention}\n\n"
            f"First summary will run at the next scheduled time."
        )
        
    except Exception as e:
        logger.error(f"Error creating category schedule: {e}", exc_info=True)
        await discord_api.followup(f"An error occurred: {str(e)}")


@bot.tree.command(name="list-schedules", description="List all active scheduled summaries")
async def list_schedules(interaction: discord.Interaction):
    """List all active scheduled summaries for this server"""
    logger.info(f"List-schedules: by '{interaction.user.name}'")
    discord_api = DiscordAPI(interaction)
    
    await discord_api.think()
    
    try:
        schedules = schedule_storage.get_all_active_schedules(interaction.guild.id)
        
        if not schedules:
            await discord_api.followup("No active scheduled summaries found for this server.")
            return
        
        # Get timezone
        timezone_str = schedule_storage.get_guild_timezone(interaction.guild.id)
        tz = pytz.timezone(timezone_str)
        
        # Build message
        message = f"**Active Scheduled Summaries** (Timezone: {timezone_str})\n\n"
        
        for i, schedule in enumerate(schedules, 1):
            schedule_id = schedule['id']
            target_name = schedule['target_name']
            schedule_type = schedule['schedule_type']
            interval_hours = schedule['interval_hours']
            start_time = schedule['start_time']
            lookback = schedule['lookback_duration']
            output_channel_id = schedule['output_channel_id']
            last_run = schedule['last_run']
            
            # Format interval
            if interval_hours == 24:
                interval_str = "daily"
            elif interval_hours % 24 == 0:
                interval_str = f"every {interval_hours // 24} days"
            else:
                interval_str = f"every {interval_hours}h"
            
            # Format last run
            if last_run:
                last_run_dt = last_run.replace(tzinfo=pytz.utc).astimezone(tz)
                now = datetime.now(tz)
                time_ago = now - last_run_dt
                if time_ago.days > 0:
                    last_run_str = f"{time_ago.days} day(s) ago"
                elif time_ago.seconds > 3600:
                    last_run_str = f"{time_ago.seconds // 3600} hour(s) ago"
                else:
                    last_run_str = f"{time_ago.seconds // 60} minute(s) ago"
            else:
                last_run_str = "Never"
            
            # Get output channel name
            output_channel = interaction.guild.get_channel(output_channel_id)
            output_str = output_channel.mention if output_channel else f"<deleted channel>"
            
            if schedule_type == 'channel':
                message += f"**{i}. ID: {schedule_id}** | #{target_name}\n"
            else:
                channel_count = len(schedule['channel_ids'])
                message += f"**{i}. ID: {schedule_id}** | Category: {target_name} ({channel_count} channels)\n"
            
            message += (
                f"   Runs: {interval_str.capitalize()} at {start_time.strftime('%H:%M')} EST\n"
                f"   Lookback: {lookback} | Posts to: {output_str}\n"
                f"   Last run: {last_run_str}\n\n"
            )
        
        # Discord has 2000 char limit, handle pagination if needed
        if len(message) > 2000:
            message = message[:1997] + "..."
        
        await discord_api.followup(message)
        
    except Exception as e:
        logger.error(f"Error listing schedules: {e}", exc_info=True)
        await discord_api.followup(f"An error occurred: {str(e)}")


@bot.tree.command(name="remove-schedule", description="Cancel a scheduled summary")
async def remove_schedule(interaction: discord.Interaction, schedule_id: int):
    """
    Remove a scheduled summary
    
    Args:
        schedule_id: The ID of the schedule to remove (from /list-schedules)
    """
    logger.info(f"Remove-schedule: by '{interaction.user.name}' for schedule #{schedule_id}")
    discord_api = DiscordAPI(interaction)
    
    await discord_api.think()
    
    try:
        # Check if schedule exists
        schedule = schedule_storage.get_schedule(schedule_id)
        
        if not schedule:
            await discord_api.followup(
                f"Schedule #{schedule_id} not found.",
                ephemeral=True
            )
            return
        
        # Check if schedule belongs to this guild
        if schedule['guild_id'] != interaction.guild.id:
            await discord_api.followup(
                "You can only remove schedules from this server.",
                ephemeral=True
            )
            return
        
        # Remove from database
        schedule_storage.delete_schedule(schedule_id)
        
        # Stop the running task
        schedule_manager.stop_schedule_task(schedule_id)
        
        target_name = schedule['target_name']
        schedule_type = schedule['schedule_type']
        
        await discord_api.followup(
            f"✅ Removed schedule #{schedule_id}\n"
            f"({schedule_type}: {target_name})"
        )
        
    except Exception as e:
        logger.error(f"Error removing schedule: {e}", exc_info=True)
        await discord_api.followup(f"An error occurred: {str(e)}")


@bot.tree.command(name="set-timezone", description="Set the timezone for scheduled summaries")
async def set_timezone(interaction: discord.Interaction, timezone: str):
    """
    Set the timezone for this server's scheduled summaries
    
    Args:
        timezone: Timezone name (e.g., 'America/New_York', 'America/Los_Angeles', 'UTC')
    """
    logger.info(f"Set-timezone: by '{interaction.user.name}' to '{timezone}'")
    discord_api = DiscordAPI(interaction)
    
    await discord_api.think()
    
    try:
        # Validate timezone
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            await discord_api.followup(
                f"Invalid timezone: '{timezone}'.\n\n"
                f"Common timezones:\n"
                f"• America/New_York (EST/EDT)\n"
                f"• America/Chicago (CST/CDT)\n"
                f"• America/Denver (MST/MDT)\n"
                f"• America/Los_Angeles (PST/PDT)\n"
                f"• UTC\n\n"
                f"See full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                ephemeral=True
            )
            return
        
        # Save timezone
        schedule_storage.set_guild_timezone(interaction.guild.id, timezone)
        
        await discord_api.followup(
            f"✅ Timezone set to: {timezone}\n\n"
            f"This will apply to all new and existing schedules on the next run."
        )
        
    except Exception as e:
        logger.error(f"Error setting timezone: {e}", exc_info=True)
        await discord_api.followup(f"An error occurred: {str(e)}")


bot.run(discord_token)
