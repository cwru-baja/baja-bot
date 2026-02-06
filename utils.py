import re
import typing
from datetime import timedelta, datetime, timezone

import discord
import webcolors

if typing.TYPE_CHECKING:
    from baja_notion.page import Page


def parse_duration(duration_str) -> timedelta:
    """Parses a duration string (e.g., '1h', '30m', '2d', '1mo') into a timedelta."""
    match = re.match(r"(\d+)(mo|[mhdw])", duration_str.lower())
    if not match:
        return timedelta()
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
    elif unit == 'mo':
        return timedelta(days=amount * 30)
    return timedelta()

def make_embed_from_part(part: "Page") -> discord.Embed:
    part_family = part.get_property("Part Family")
    primary_designer = part.get_property("Primary Designer")

    color_str = part_family.value[0]["color"] if part_family else "gray"

    hex_color = parse_color(color_str)

    designer_name = primary_designer.value[0]["name"]

    # pyperclip.copy(json.dumps(part.raw_json))
    part_title = make_part_title(part)

    embed = discord.Embed(
        title=part_title,
        color=discord.Color.from_str(hex_color)
    )

    design_status = part.get_property("Design Status")
    analysis_status = part.get_property("Analysis Status")
    mfg_status = part.get_property("Mfg Status")
    embed.add_field(name="Design Status", value=design_status.value["name"], inline=True) if design_status else None
    embed.add_field(name="Analysis Status", value=analysis_status.value["name"],
                    inline=True) if analysis_status else None
    embed.add_field(name="Mfg Status", value=mfg_status.value["name"], inline=True) if mfg_status else None

    # Line break
    # embed.add_field(name="\u200b", value="\u200b", inline=False)

    po_status = part.get_property("PO Status")
    embed.add_field(name="PO Status", value=po_status.value["name"], inline=True) if po_status else None

    # embed.add_field(name="\u200b", value="\u200b", inline=False)

    material = part.get_property("Material")
    stock_shape = part.get_property("Stock Shape")
    mfg_process = part.get_property("Mfg Process(es)")
    embed.add_field(name="Material", value=material.value[0]["name"], inline=True) if material else None
    embed.add_field(name="Stock Shape", value=stock_shape.value[0]["name"], inline=True) if stock_shape else None
    if mfg_process:
        machines = ", ".join([mach["name"] for mach in mfg_process.value])
        embed.add_field(name="Machine", value=machines, inline=True)

    # embed.add_field(name="\u200b", value="\u200b", inline=False)

    qty_made = part.get_property("Qty Made")
    qty_car = part.get_property("Qty on Car")

    embed.add_field(name="Qty Made", value=qty_made.value if qty_made is not None else "Not Reported", inline=True)
    embed.add_field(name="Qty on Car", value=qty_car.value, inline=True) if qty_car else None

    return embed

def make_part_title(part: "Page") -> str:
    part_name = part.get_property("Part Name")
    part_number = part.get_property("Part Number")
    part_name_val = part_name.value[0]["plain_text"].strip() if part_name else ""
    part_num_val = part_number.value[0]["plain_text"].strip() if part_number else ""
    if part_number and part_name:
        part_title = f"{part_name_val}: {part_num_val}"
    elif part_name:
        part_title = f"{part_name_val}"
    elif part_number:
        part_title = f"{part_num_val}"
    else:
        part_title = f"No part name or number?"
    return part_title

def parse_color(color: str) -> str:
    """Converts a notion color into a hex string"""
    try:
        hex_color = webcolors.name_to_hex(color)
    except ValueError:
        hex_color = webcolors.name_to_hex("gray")
    return hex_color

def parse_time_utc(time: str, format_str: str="%Y-%m-%dT%H:%M:%S.%fZ") -> datetime:
    return datetime.strptime(time, format_str).replace(tzinfo=timezone.utc)


def normalize_category_name(name: str) -> str:
    """Normalize category names for matching (strip emoji/punctuation, lowercase)."""
    if not name:
        return ""
    # Keep letters, digits, spaces, underscores, and hyphens; drop emoji/punctuation.
    cleaned = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip().lower()