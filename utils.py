from datetime import timedelta
import re


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