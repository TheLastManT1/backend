def get_compass_direction(degrees):
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = round(degrees / 22.5) % 16
    return directions[index]

def get_weather_condition(weather_code, is_day):
    icon = 1
    text = "Unknown"

    if is_day:
        if weather_code == 0: # Clear sky
            icon, text = 1, "Sunny"
        elif weather_code == 1: # Mainly clear
            icon, text = 2, "Mostly Sunny"
        elif weather_code == 2: # Partly cloudy
            icon, text = 3, "Partly Sunny"
        elif weather_code == 3: # Overcast
            icon, text = 7, "Cloudy" # Closest to Mostly Cloudy/Cloudy
        elif weather_code in [45, 48]: # Fog and depositing rime fog
            icon, text = 11, "Fog"
        elif weather_code in [51, 53, 55]: # Drizzle
            icon, text = 12, "Showers" # Or 18 for Rain
        elif weather_code in [56, 57]: # Freezing Drizzle
            icon, text = 26, "Freezing Rain"
        elif weather_code in [61, 63, 65]: # Rain
            icon, text = 18, "Rain"
        elif weather_code in [66, 67]: # Freezing Rain
            icon, text = 26, "Freezing Rain"
        elif weather_code in [71, 73, 75, 77]: # Snow fall, Snow grains
            icon, text = 22, "Snow"
        elif weather_code in [80, 81, 82]: # Rain showers
            icon, text = 12, "Showers"
        elif weather_code in [85, 86]: # Snow showers
            icon, text = 22, "Snow"
        elif weather_code == 95: # Thunderstorm
            icon, text = 15, "Thunderstorms"
        elif weather_code in [96, 99]: # Thunderstorm with hail
            icon, text = 15, "Thunderstorms" # Closest
        else:
            icon, text = 1, "Unknown" # Fallback for unmapped codes
    else: # Night
        if weather_code == 0: # Clear sky
            icon, text = 33, "Clear"
        elif weather_code == 1: # Mainly clear
            icon, text = 34, "Mostly clear"
        elif weather_code == 2: # Partly cloudy
            icon, text = 35, "Intermittent clouds" # Closest to partly cloudy at night
        elif weather_code == 3: # Overcast
            icon, text = 37, "Mostly cloudy"
        elif weather_code in [45, 48]: # Fog and depositing rime fog
            icon, text = 11, "Fog" # Same as day for fog
        elif weather_code in [51, 53, 55]: # Drizzle
            icon, text = 38, "Partly cloudy with Showers" # Closest to rain/drizzle at night
        elif weather_code in [56, 57]: # Freezing Drizzle
            icon, text = 26, "Freezing Rain" # Same as day
        elif weather_code in [61, 63, 65]: # Rain
            icon, text = 38, "Partly cloudy with Showers" # Closest to rain at night
        elif weather_code in [66, 67]: # Freezing Rain
            icon, text = 26, "Freezing Rain" # Same as day
        elif weather_code in [71, 73, 75, 77]: # Snow fall, Snow grains
            icon, text = 42, "Mostly cloudy with Flurries" # Closest to snow at night
        elif weather_code in [80, 81, 82]: # Rain showers
            icon, text = 38, "Partly cloudy with Showers"
        elif weather_code in [85, 86]: # Snow showers
            icon, text = 42, "Mostly cloudy with Flurries" # Closest to snow at night
        elif weather_code == 95: # Thunderstorm
            icon, text = 40, "Partly cloudy with Thunder Showers"
        elif weather_code in [96, 99]: # Thunderstorm with hail
            icon, text = 40, "Partly cloudy with Thunder Showers" # Closest
        else:
            icon, text = 33, "Unknown"

    return icon, text


import requests
import json
import time


def get_nominatim_reverse(lat: float, lon: float, attempts: int = 3, timeout: int = 5):
    nominatim_reverse_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1"
    headers = {"User-Agent": "HTC HTTP Service"}

    for attempt in range(attempts):
        try:
            resp = requests.get(nominatim_reverse_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Nominatim API call failed (attempt {attempt + 1}/{attempts}): {e}")
            if attempt == attempts - 1:
                return None
            time.sleep(0.5)


def search_nominatim(city: str, country_code: str, attempts: int = 3, timeout: int = 5):
    q = f"{city},{country_code}"
    nominatim_search_url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&addressdetails=1"
    headers = {"User-Agent": "HTC HTTP Service"}

    for attempt in range(attempts):
        try:
            resp = requests.get(nominatim_search_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data_list = resp.json()
            if data_list:
                return data_list[0]
            # No results is considered a valid response; return None
            return None
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Nominatim search failed (attempt {attempt + 1}/{attempts}): {e}")
            if attempt == attempts - 1:
                return None
            time.sleep(0.5)


def fetch_open_meteo(lat: float, lon: float, forecast_days: int = 5, attempts: int = 3, timeout: int = 5):
    daily_fields = "temperature_2m_max,temperature_2m_min,windspeed_10m_max,winddirection_10m_dominant,uv_index_max,weathercode,sunrise,sunset"
    hourly_fields = "temperature_2m,windspeed_10m,winddirection_10m,weathercode,precipitation"

    open_meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true&forecast_days={forecast_days}&"
        f"daily={daily_fields}&"
        f"hourly={hourly_fields}&"
        f"timezone=auto"
    )

    for attempt in range(attempts):
        try:
            resp = requests.get(open_meteo_url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Open-Meteo API call failed (attempt {attempt + 1}/{attempts}): {e}")
            if attempt == attempts - 1:
                return None
            time.sleep(0.5)


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def get_timezone_info(timezone_name: str, dt: datetime = None):
    tz = ZoneInfo(timezone_name)
    if dt is None:
        dt = datetime.now(tz)

    current_offset = dt.utcoffset() or timedelta(0)
    current_gmt_offset = current_offset.total_seconds() / 3600

    dst_offset = dt.dst() or timedelta(0)
    is_dst = bool(dst_offset and dst_offset != timedelta(0))

    standard_offset = current_offset - dst_offset
    standard_gmt_offset = standard_offset.total_seconds() / 3600

    abbreviation = dt.tzname()

    uses_dst = False
    for month in range(1, 13):
        test_dt = datetime(dt.year, month, 1, tzinfo=tz)
        if test_dt.dst() != timedelta(0):
            uses_dst = True
            break

    return {
        "timeZone": standard_gmt_offset,
        "currentGmtOffset": current_gmt_offset,
        "timeZoneAbbreviation": abbreviation,
        "is_dst": is_dst,
        "uses_dst": uses_dst
    }


def to_12h_format(time_str: str) -> str:
    # expects HH:MM or HH:MM:SS (we'll take first 5 chars)
    s = time_str[:5]
    t = datetime.strptime(s, "%H:%M")
    hour_12 = t.strftime("%I").lstrip("0")
    minute = t.strftime("%M")
    ampm = t.strftime("%p")
    return f"{hour_12}:{minute} {ampm}"


def uv_index_to_text(index: float) -> str:
    if index < 0:
        return "Invalid"
    elif index <= 2:
        return "Low"
    elif index <= 5:
        return "Moderate"
    elif index <= 7:
        return "High"
    elif index <= 10:
        return "Very High"
    else:
        return "Extreme"


def format_to_mdyyyy(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}/{dt.day}/{dt.year}"


def get_weekday_name(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%A")


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


def convert_temperature(temp, metric):
    # metric: truthy -> Celsius, falsy -> Fahrenheit
    if not metric:
        return c_to_f(temp)
    else:
        return temp


def kmh_to_mph(kmh):
    return kmh * 0.621371


def mps_to_mph(mps):
    return mps * 2.2369362920544


def convert_speed(speed, metric):
    if not metric:
        return kmh_to_mph(speed)
    else:
        return speed