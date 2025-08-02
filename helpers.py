from config import app

@app.template_filter()
def format_datetime(value, format='iso'):
    if format == 'iso':
        return value.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    return value.strftime(format)

@app.template_filter()
def iso8601_to_seconds(value):
    total_seconds = 0

    import re
    match = re.match(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', value)

    if not match:
        raise ValueError("Invalid ISO 8601 duration string format.")

    days, hours, minutes, seconds = match.groups()

    if days:
        total_seconds += int(days) * 24 * 60 * 60
    if hours:
        total_seconds += int(hours) * 60 * 60
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)

    return total_seconds