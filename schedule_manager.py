import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Dict
import pytz
import discord
from discord.ext import tasks

from summarizer import Summarizer
from discord_api import DiscordAPI
from utils import parse_duration

"""
Schedule manager for handling scheduled summary tasks.
Creates and manages discord.ext.tasks loops for each schedule.
"""

logger = logging.getLogger(__name__)

# Global dictionary to track active schedule tasks
active_schedule_tasks = {}  # {schedule_id: Task}


async def load_all_schedules(bot, storage, ai_client):
    """
    Load all active schedules from database and start their tasks
    
    Args:
        bot: Discord bot instance
        storage: ScheduleStorage instance
        ai_client: AI API client
    """
    try:
        schedules = storage.get_all_active_schedules()
        logger.info(f"Loading {len(schedules)} scheduled summaries from database...")
        
        for schedule in schedules:
            try:
                task = create_schedule_task(schedule, bot, storage, ai_client)
                task.start()
                active_schedule_tasks[schedule['id']] = task
                logger.info(f"Started schedule #{schedule['id']}: {schedule['target_name']}")
            except Exception as e:
                logger.error(f"Failed to start schedule #{schedule['id']}: {e}")
        
        logger.info(f"Successfully loaded {len(active_schedule_tasks)} schedules")
    except Exception as e:
        logger.error(f"Error loading schedules: {e}")


def create_schedule_task(schedule: Dict, bot, storage, ai_client):
    """
    Create a discord.ext.tasks loop for a schedule
    
    Args:
        schedule: Schedule dictionary from database
        bot: Discord bot instance
        storage: ScheduleStorage instance
        ai_client: AI API client
        
    Returns:
        A tasks.loop task instance
    """
    interval_hours = schedule['interval_hours']
    schedule_id = schedule['id']
    
    @tasks.loop(hours=interval_hours)
    async def scheduled_task():
        """The actual task that runs on schedule"""
        try:
            await run_scheduled_summary(schedule, bot, storage, ai_client)
        except Exception as e:
            logger.error(f"Error running schedule #{schedule_id}: {e}")
    
    # Set up the before_loop to wait until the start time
    @scheduled_task.before_loop
    async def before_task():
        await bot.wait_until_ready()
        
        # Get guild timezone
        guild_id = schedule['guild_id']
        timezone_str = storage.get_guild_timezone(guild_id)
        
        # Wait until the scheduled start time
        await wait_until_start_time(schedule['start_time'], timezone_str)
    
    return scheduled_task


async def wait_until_start_time(start_time: dt_time, timezone_str: str):
    """
    Wait until the specified start time in the given timezone
    
    Args:
        start_time: Time of day to start (time object)
        timezone_str: Timezone string (e.g., 'America/New_York')
    """
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)
    
    # Create datetime for today at the start time
    target = tz.localize(datetime.combine(now.date(), start_time))
    
    # If the time has already passed today, schedule for tomorrow
    if target <= now:
        target = target + timedelta(days=1)
    
    # Calculate wait time
    wait_seconds = (target - now).total_seconds()
    
    logger.info(f"Waiting {wait_seconds/3600:.2f} hours until {target.strftime('%Y-%m-%d %H:%M %Z')}")
    
    await discord.utils.sleep_until(target)


async def run_scheduled_summary(schedule: Dict, bot, storage, ai_client):
    """
    Execute a scheduled summary
    
    Args:
        schedule: Schedule dictionary from database
        bot: Discord bot instance
        storage: ScheduleStorage instance
        ai_client: AI API client
    """
    schedule_id = schedule['id']
    guild_id = schedule['guild_id']
    channel_ids = schedule['channel_ids']
    output_channel_id = schedule['output_channel_id']
    lookback_duration = schedule['lookback_duration']
    schedule_type = schedule['schedule_type']
    target_name = schedule['target_name']
    
    logger.info(f"Running schedule #{schedule_id}: {target_name}")
    
    try:
        # Get the guild
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild {guild_id} not found for schedule #{schedule_id}")
            return
        
        # Get output channel
        output_channel = guild.get_channel(output_channel_id)
        if not output_channel:
            logger.error(f"Output channel {output_channel_id} not found for schedule #{schedule_id}")
            return
        
        # Parse lookback duration
        delta = parse_duration(lookback_duration)
        if not delta:
            logger.error(f"Invalid lookback duration '{lookback_duration}' for schedule #{schedule_id}")
            return
        
        cutoff_time = datetime.now(pytz.utc) - delta
        summarizer = Summarizer(ai_client)
        
        # Handle different schedule types
        if schedule_type == 'channel':
            # Single channel summary
            await run_channel_summary(
                guild, channel_ids[0], cutoff_time, 
                summarizer, output_channel, target_name, lookback_duration
            )
        elif schedule_type == 'category':
            # Category summary with sections
            await run_category_summary(
                guild, channel_ids, cutoff_time, 
                summarizer, output_channel, target_name, lookback_duration
            )
        
        # Update last run timestamp
        storage.update_last_run(schedule_id)
        logger.info(f"Completed schedule #{schedule_id}")
        
    except Exception as e:
        logger.error(f"Error executing schedule #{schedule_id}: {e}", exc_info=True)


async def run_channel_summary(guild, channel_id, cutoff_time, summarizer, output_channel, channel_name, lookback_duration):
    """Run summary for a single channel"""
    channel = guild.get_channel(channel_id)
    if not channel:
        logger.warning(f"Channel {channel_id} not found")
        await output_channel.send(f"⚠️ Could not find channel for scheduled summary: {channel_name}")
        return
    
    # Fetch messages from the channel and its threads
    messages = await fetch_messages_with_threads(channel, cutoff_time)
    
    if not messages:
        logger.info(f"No messages in {channel_name} since {cutoff_time}")
        return
    
    # Generate summary
    summary = await summarizer.get_summary(messages)
    
    # Post to output channel (ensure message length limits)
    header = f"**Scheduled Summary: {channel.mention}** (Last {lookback_duration})"
    for message in build_summary_messages(header, summary):
        await output_channel.send(message)


async def run_category_summary(guild, channel_ids, cutoff_time, summarizer, output_channel, category_name, lookback_duration):
    """Run summary for a category (multiple channels with sections)"""
    channel_messages = {}
    
    # Fetch messages from each channel
    for channel_id in channel_ids:
        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(f"Channel {channel_id} not found in category")
            continue
        
        messages = await fetch_messages_with_threads(channel, cutoff_time)
        
        if messages:
            channel_messages[channel.name] = messages
    
    if not channel_messages:
        logger.info(f"No messages in category {category_name} since {cutoff_time}")
        return
    
    # Generate sectioned summary
    summary = await summarizer.get_sectioned_summary(channel_messages)
    
    # Post to output channel (ensure message length limits)
    header = f"**Scheduled Summary: Category '{category_name}'** (Last {lookback_duration})"
    for message in build_summary_messages(header, summary):
        await output_channel.send(message)


async def fetch_messages_with_threads(channel, cutoff_time, limit=500):
    """Fetch messages for a text channel and all threads within the timeframe."""
    messages = []

    # Channel history
    async for message in channel.history(limit=limit, after=cutoff_time, oldest_first=True):
        messages.append(message)

    # Collect active threads
    thread_ids = set()
    threads = []
    for thread in getattr(channel, "threads", []):
        if thread.id not in thread_ids:
            thread_ids.add(thread.id)
            threads.append(thread)

    # Collect archived threads (public and private if permitted)
    try:
        async for thread in channel.archived_threads(limit=None):
            if thread.id not in thread_ids:
                thread_ids.add(thread.id)
                threads.append(thread)
    except Exception as e:
        logger.warning(f"Failed to fetch archived threads for #{channel.name}: {e}")

    try:
        async for thread in channel.archived_threads(limit=None, private=True):
            if thread.id not in thread_ids:
                thread_ids.add(thread.id)
                threads.append(thread)
    except Exception as e:
        logger.warning(f"Failed to fetch private archived threads for #{channel.name}: {e}")

    # Thread histories
    for thread in threads:
        try:
            async for message in thread.history(limit=limit, after=cutoff_time, oldest_first=True):
                messages.append(message)
        except Exception as e:
            logger.warning(f"Failed to fetch thread history for '{thread.name}': {e}")

    # Sort for consistent ordering
    messages.sort(key=lambda msg: msg.created_at)
    return messages


def build_summary_messages(header: str, summary: str, max_len: int = 2000):
    """Build one or more messages that stay within Discord's length limit."""
    header = header.strip()
    summary = summary.strip()
    first_prefix = f"{header}\n\n"
    first_max = max_len - len(first_prefix)
    if first_max <= 0:
        return [header[:max_len]]

    first_chunk, remaining = take_text_chunk(summary, first_max)
    messages = [first_prefix + first_chunk]

    cont_prefix = "Summary (continued):\n\n"
    cont_max = max_len - len(cont_prefix)
    while remaining:
        chunk, remaining = take_text_chunk(remaining, cont_max)
        messages.append(cont_prefix + chunk)

    return messages


def take_text_chunk(text: str, max_len: int):
    """Take a chunk up to max_len, prefer paragraph or line breaks."""
    if len(text) <= max_len:
        return text, ""

    split_at = text.rfind("\n\n", 0, max_len)
    if split_at == -1:
        split_at = text.rfind("\n", 0, max_len)
    if split_at == -1:
        split_at = max_len

    chunk = text[:split_at].rstrip()
    remaining = text[split_at:].lstrip()
    return chunk, remaining


def start_schedule_task(schedule_id: int, task):
    """
    Add a task to the active tasks dictionary and start it
    
    Args:
        schedule_id: The schedule ID
        task: The tasks.loop task instance
    """
    active_schedule_tasks[schedule_id] = task
    task.start()


def stop_schedule_task(schedule_id: int):
    """
    Stop and remove a running scheduled task
    
    Args:
        schedule_id: The schedule ID to stop
    """
    if schedule_id in active_schedule_tasks:
        task = active_schedule_tasks[schedule_id]
        task.cancel()
        del active_schedule_tasks[schedule_id]
        logger.info(f"Stopped schedule #{schedule_id}")
