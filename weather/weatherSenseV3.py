"""
Original server: http://htc2.accu-weather.com
Archived sample: http://htc2.accu-weather.com/widget/htc2/weather-data.asp?location=EUR%7CGR%7CGR020%7CIRACLION&metric=0

This should work for all HTC Sense 3 devices
Although a large amount of data is missing, I tried to fake some reasonable values and it seems working fine
"""
from config import app
import weather.helpers
from flask import render_template, request, Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
import json
from time import sleep

def get_timezone_info(timezone_name: str, dt: datetime = None):
    """
    Parameters:
        timezone_name: IANA timezone name, e.g. "Asia/Tokyo", "Europe/Athens"
        dt: specified datetime, defaults to the current local time
    Returns:
        {
            "timeZone": standard timezone offset (without DST),
            "currentGmtOffset": current actual offset (including DST),
            "timeZoneAbbreviation": current timezone abbreviation,
            "is_dst": whether currently in daylight saving time,
            "uses_dst": whether the timezone has DST rules (past or future)
        }
    """
    tz = ZoneInfo(timezone_name)
    
    # If no time is provided, use the current local time
    if dt is None:
        dt = datetime.now(tz)

    # Current offset (including DST)
    current_offset = dt.utcoffset()
    current_gmt_offset = current_offset.total_seconds() / 3600

    # Get DST offset (if nonzero, currently in DST)
    dst_offset = dt.dst()
    is_dst = bool(dst_offset and dst_offset != timedelta(0))

    # Calculate standard offset: current offset - DST offset
    standard_offset = current_offset - (dst_offset or timedelta(0))
    standard_gmt_offset = standard_offset.total_seconds() / 3600

    # Get timezone abbreviation (e.g., JST, EET, EEST, EDT, EST)
    abbreviation = dt.tzname()

    # Determine whether this timezone has had or will have DST rules
    # Simple method: check if there is any moment within a year where dst() is nonzero
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

def weathercode_to_name(code: int) -> str:
    """
    Convert WMO weather code to standard English description
    """
    mapping = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm (slight or moderate)",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return mapping.get(code, "Unknown weather code")

def to_12h_format(time_str: str) -> str:
    """
    Convert a 24-hour time string (e.g. "18:30") to 12-hour format with AM/PM (e.g. "6:30 PM").
    Cross-platform compatible (Windows/Linux/macOS).
    """
    from datetime import datetime
    # Parse 24-hour time
    t = datetime.strptime(time_str, "%H:%M")
    # Format as 12-hour time (%I gives 01–12, remove leading zero)
    hour_12 = t.strftime("%I").lstrip("0")  # remove leading zero
    minute = t.strftime("%M")
    ampm = t.strftime("%p")
    return f"{hour_12}:{minute} {ampm}"

def uv_index_to_text(index: float) -> str:
    """
    Convert UV index value to a descriptive text.
    Reference scale:
    0–2      Low
    3–5      Moderate
    6–7      High
    8–10     Very High
    11+      Extreme
    """
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
    """
    Convert a date from 'YYYY-MM-DD' format to 'M/D/YYYY' format.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}/{dt.day}/{dt.year}"

def get_weekday_name(date_str: str) -> str:
    """
    Convert a date in 'YYYY-MM-DD' format to the English weekday name (capitalized).
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%A")  # output Monday, Tuesday, ...

def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0

def convert_temperature(temp, metric):
    if not metric: return c_to_f(temp)
    else: return temp

def kmh_to_mph(kmh):
    return kmh * 0.621371

def mps_to_mph(mps):
    return mps * 2.2369362920544

def convert_speed(speed, metric):
    if not metric: return kmh_to_mph(speed)
    else: return speed

@app.route("/widget/htc2/weather-data.asp", methods=["GET"])
def weather_data_htc2():
    """
      - location=ASI|CN|CH016|GANZHOU   (same format as locCode)
      - metric=0  -> (F, MPH, MI, IN)
      - metric=1  -> (C, KM/H, KM, MB)
    """
    # get parameters
    location_code = request.args.get("location", "ASI|TW|TW018|TAIPEI")
    metric = request.args.get("metric", "1")
    use_metric = (metric == "1")

    # parse location_code
    try:
        continent, country_code, state_code, city_name_short = location_code.split("|")
    except Exception:
        return "Bad location format", 400

    # Nominatim search for city latitude and longitude
    nominatim_search_url = f"https://nominatim.openstreetmap.org/search?q={city_name_short},{country_code}&format=json&limit=1&addressdetails=1"
    headers = {'User-Agent': 'HTC HTTP Service'}

    nominatim_data = {}
    lat = 0.0
    lon = 0.0
    city = city_name_short
    country = country_code

    for attempt in range(3):
        try:
            r = requests.get(nominatim_search_url, headers=headers, timeout=5)
            r.raise_for_status()
            data_list = r.json()
            if data_list:
                nominatim_data = data_list[0]
                lat = float(nominatim_data.get("lat", "0.0"))
                lon = float(nominatim_data.get("lon", "0.0"))
                addr = nominatim_data.get("address", {})
                city = addr.get("city", addr.get("town", addr.get("village", city_name_short)))
                country = addr.get("country", country_code)
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Nominatim API failed (attempt {attempt+1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve location data.", 500
            sleep(0.5)

    # request weather data from Open-Meteo（timezone=auto return local time）
    open_meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true&forecast_days=9&"
        f"daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,winddirection_10m_dominant,uv_index_max,weathercode,sunrise,sunset&"
        f"hourly=temperature_2m,windspeed_10m,winddirection_10m,weathercode,precipitation&"
        f"timezone=auto"
    )

    weather_data = {}
    for attempt in range(3):
        try:
            r = requests.get(open_meteo_url, timeout=5)
            r.raise_for_status()
            weather_data = r.json()
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Open-Meteo API failed (attempt {attempt+1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve weather data.", 500
            sleep(0.5)

    #================================Units================================
    units = {
        "temp": "C" if use_metric else "F",
        "dist": "KM" if use_metric else "MI",
        "speed": "KM/H" if use_metric else "MPH",
        "pres": "MB" if use_metric else "IN",
        "prec": "MM" if use_metric else "IN"
    }

    #================================local================================
    timeInfo = get_timezone_info(weather_data.get("timezone", "Asia/Tokyo"))
    local = {
        "city": city,
        "adminArea": {"code": state_code, "name": state_code}, #TD: the name should query a real one
        "country": {"code": country_code, "name": country},
        "lat": f"{lat:.5f}",
        "lon": f"{lon:.5f}",
        "time": weather_data["current_weather"]["time"][-5:],
        "timeZone": int(timeInfo["timeZone"]),
        "obsDaylight": weather_data["current_weather"]["is_day"],
        "currentGmtOffset": int(timeInfo["currentGmtOffset"]),
        "timeZoneAbbreviation": timeInfo["timeZoneAbbreviation"]
    }

    #==========================currentconditions==========================
    weatherInfo = weather.helpers.get_weather_condition(weather_data["current_weather"]["weathercode"], local["obsDaylight"])
    currentconditions = {
        "daylight": "True" if weather_data["current_weather"]["is_day"] else "False",
        "url": "http://www.accuweather.com/m/en-us/GR/M/Iraklio/current.aspx?p=htc2&amp;cityId=2282907", #TD: just a placeholder, this data doesn’t exist yet
        "observationtime": to_12h_format(local["time"]),
        "pressure": {"value": "99.90", "state": "UNKNOWN"}, #TD: I don't have this information yet
        "temperature": round(convert_temperature(weather_data["current_weather"]["temperature"], use_metric)),
        "realfeel": "99", #TD: I don't have this information yet
        "humidity": "50%", #TD: I don't have this information yet
        "weathertext": weatherInfo[1],
        "weathericon": weatherInfo[0],
        #"weathertext": weathercode_to_name(weather_data["current_weather"]["weathercode"]),
        #"weathericon": ("0" + weather_data["current_weather"]["weathercode"]) if len(weather_data["current_weather"]["weathercode"]) == 1 else weather_data["current_weather"]["weathercode"],
        "windgusts": round(convert_speed(weather_data["current_weather"]["windspeed"], use_metric)), #TD: I don't have this information yet
        "windspeed": round(convert_speed(weather_data["current_weather"]["windspeed"], use_metric)),
        "winddirection": weather.helpers.get_compass_direction(weather_data["current_weather"]["winddirection"]),
        "visibility": "10", #TD: I don't have this information yet
        "precip": weather_data["hourly"]["precipitation"][int(local["time"][0:2])],
        "uvindex": {"index": round(weather_data["daily"]["uv_index_max"][0]), "text": uv_index_to_text(weather_data["daily"]["uv_index_max"][0])},
        "dewpoint": "55", #TD: I don't have this information yet
        "cloudcover": "50%", #TD: I don't have this information yet
        "apparenttemp": round(convert_temperature(weather_data["current_weather"]["temperature"], use_metric)), #TD: I don't have this information yet
        "windchill": round(convert_temperature(weather_data["current_weather"]["temperature"], use_metric)) #TD: I don't have this information yet
    }

    #===============================planets===============================
     #TD: I don't have other planets information
    planets = {
		"sun":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"moon":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"mercury":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"venus":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"mars":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"jupiter":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"saturn":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"uranus":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"neptune":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])},
		"pluto":{"sunrise":to_12h_format(weather_data["daily"]["sunrise"][0][-5:]), "sunset":to_12h_format(weather_data["daily"]["sunset"][0][-5:])}
    }

    #================================moon================================
    #TD: I don't have this information yet, so I have to fake one
    # moon phase list, used in loop
    moon_phases = [
        "New", "Waxing Crescent", "First", "Waxing Gibbous", 
        "Full", "Waning Gibbous", "Last", "Waning Crescent"
    ]

    # assume it start from today
    start_date = datetime.today() 
    days_to_generate = 32 # according to sample, it need 32 days data
    moon = []
    for i in range(days_to_generate):
        date = (start_date + timedelta(days=i)).strftime("%m/%d/%Y")
        age = (i % 29) + 1  # Lunar age 1–29 (repeats cyclically)
        # Lunar phase selection: cycles through 8 phases, each lasting about 3–4 days
        text = moon_phases[(i // 4) % len(moon_phases)]
        moon.append({'date': date, 'text': text, 'age': age})

    #============================forecast_url============================
    forecast_url = "http://www.accuweather.com/m/en-us/GR/M/Iraklio/forecast.aspx?p=htc2&amp;cityId=2282907" #TD: just a placeholder, this data doesn’t exist yet

    #============================forecast_days============================
    days_to_generate = 9 # according to sample, it need nine days data
    forecast_days = []
    for i in range(days_to_generate):
        date = weather_data["daily"]["time"][i]
        sunrise = weather_data["daily"]["sunrise"][i][-5:]
        sunset = weather_data["daily"]["sunset"][i][-5:]
        weathercode = weather_data["daily"]["weathercode"][i]
        tempMax = weather_data["daily"]["temperature_2m_max"][i]
        tempMin = weather_data["daily"]["temperature_2m_min"][i]
        windspeed = weather_data["daily"]["windspeed_10m_max"][i]
        winddirection = weather_data["daily"]["winddirection_10m_dominant"][i]
        maxuv = weather_data["daily"]["uv_index_max"][i]
        day_dict = {
            "number": i + 1,
            "url": f"http://www.accuweather.com/m/en-us/GR/M/Iraklio/details{i+1}.aspx?p=htc2&cityId=2282907", #TD: just a placeholder, this data doesn’t exist yet
            "obsdate": format_to_mdyyyy(date),
            "daycode": get_weekday_name(date),
            "sunrise": to_12h_format(sunrise),
            "sunset": to_12h_format(sunset),
            "day_txtshort": "Partly Cloudy", #TD: I don't know the standard, so I have to place the original
            "day_txtlong": "Partly cloudy with some sun", #TD: I don't know the standard, so I have to place the original
            "day_icon": weather.helpers.get_weather_condition(weathercode, 1)[0],
            "day_high": round(convert_temperature(tempMax, use_metric)),
            "day_low": round(convert_temperature(tempMin, use_metric)),
            "day_realfeelhigh": round(convert_temperature(tempMax, use_metric)), #TD: I don't have this information yet
            "day_realfeellow": round(convert_temperature(tempMin, use_metric)), #TD: I don't have this information yet
            "day_windspeed": round(convert_speed(windspeed, use_metric)),
            "day_winddirection": weather.helpers.get_compass_direction(winddirection),
            "day_windgust": round(convert_speed(windspeed, use_metric)), #TD: I don't have this information yet
            "day_maxuv": round(maxuv),
            "day_rain": "0.00", #TD: I don't have this information yet
            "day_snow": "0.0", #TD: I don't have this information yet
            "day_ice": "0.00", #TD: I don't have this information yet
            "day_precip": "0.00", #TD: I don't have this information yet
            "day_tstormprob": 0, #TD: I don't have this information yet
            "night_txtshort": "Clear", #TD: I don't know the standard, so I have to place the original
            "night_txtlong": "Clear skies", #TD: I don't know the standard, so I have to place the original
            "night_icon": weather.helpers.get_weather_condition(weathercode, 0)[0],
            "night_high": round(convert_temperature(tempMax, use_metric)),
            "night_low": round(convert_temperature(tempMin, use_metric)),
            "night_realfeelhigh": round(convert_temperature(tempMax, use_metric)), #TD: I don't have this information yet
            "night_realfeellow": round(convert_temperature(tempMin, use_metric)), #TD: I don't have this information yet
            "night_windspeed": round(convert_speed(windspeed, use_metric)),
            "night_winddirection": weather.helpers.get_compass_direction(winddirection),
            "night_windgust": round(convert_speed(windspeed, use_metric)), #TD: I don't have this information yet
            "night_maxuv": maxuv,
            "night_rain": "0.00", #TD: I don't have this information yet
            "night_snow": "0.0", #TD: I don't have this information yet
            "night_ice": "0.00", #TD: I don't have this information yet
            "night_precip": "0.00", #TD: I don't have this information yet
            "night_tstormprob": 0 #TD: I don't have this information yet
        }
        forecast_days.append(day_dict)

    #===========================forecast_hours============================
    forecast_hours = []
    for i in range(24):
        time = weather_data["hourly"]["time"][i][-5:]
        weathercode = weather_data["hourly"]["weathercode"][i]
        temp = weather_data["hourly"]["temperature_2m"][i]
        precip = weather_data["hourly"]["precipitation"][i]
        windspeed = weather_data["hourly"]["windspeed_10m"][i]
        winddirection = weather_data["hourly"]["winddirection_10m"][i]
        isDay = True if time > weather_data["daily"]["sunrise"][0][-5:] and time < weather_data["daily"]["sunset"][0][-5:] else False
        forecast_hours.append({
            "time": to_12h_format(time)[:-6] + to_12h_format(time)[-3:],
            "icon": weather.helpers.get_weather_condition(weathercode, isDay)[0],
            "temp": round(convert_temperature(temp, use_metric)),
            "realfeel": round(convert_temperature(temp, use_metric)),
            "precip": round(precip),
            "windspeed": round(convert_speed(windspeed, use_metric)),
            "winddirection": weather.helpers.get_compass_direction(winddirection),
            "text": "Partly Cloudy",
            "obsdate": forecast_days[0]["obsdate"],
            "mobileLink": "http://www.accuweather.com/m/en-us/GR/M/Iraklio/hourly13.aspx?partner=htc2&amp;cityId=2282907" #TD: just a placeholder, this data doesn’t exist yet
        })
    # only by doing this can hourly view work
    forecast_hours = forecast_hours[13:] + forecast_hours[:13]
   
    #===========================render template==========================
    template_context = {
        "units": units,
        "local": local,
        "currentconditions": currentconditions,
        "planets": planets,
        "moon": moon,
        "forecast_url": forecast_url,
        "forecast_days": forecast_days,
        "forecast_hours": forecast_hours,
        "product": "htc2 feed",
        "copyright_year": datetime.utcnow().year
    }

    response_xml = render_template("weatherSence3x.xml", **template_context)
    return Response(response_xml, mimetype="application/xml; charset=utf-8")

