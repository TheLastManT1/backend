from config import app
import weather.helpers
from flask import render_template, request, Response
from datetime import datetime, timedelta
import requests
import pytz
import json
from time import sleep

@app.route("/getweather", methods=["GET"])
@app.route("/lat-lon-search.asp", methods=["GET"])
@app.route("/widget/htc/lat-lon-search.asp", methods=["GET"])
def getweather():
    lat = float(request.args.get("lat", "0"))
    lon = float(request.args.get("lon", "0"))

    nominatim_reverse_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1"
    headers = {'User-Agent': 'HTC HTTP Service'}
    
    nominatim_data = {}
    for attempt in range(3):
        try:
            nominatim_response = requests.get(nominatim_reverse_url, headers=headers, timeout=5)
            nominatim_response.raise_for_status()
            nominatim_data = nominatim_response.json()
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Nominatim API call failed (attempt {attempt + 1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve location data.", 500
            sleep(0.5)

    city = nominatim_data.get("address", {}).get("city", nominatim_data.get("address", {}).get("town", nominatim_data.get("address", {}).get("village", "Unknown City")))
    country = nominatim_data.get("address", {}).get("country", "Unknown Country")

    open_meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true&forecast_days=5&"
        f"daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,winddirection_10m_dominant,uv_index_max,weathercode,sunrise,sunset&"
        f"hourly=temperature_2m,windspeed_10m,winddirection_10m,weathercode&"
        f"timezone=auto"
    )

    weather_data = {}
    for attempt in range(3):
        try:
            weather_response = requests.get(open_meteo_url, timeout=5)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Open-Meteo API call failed (attempt {attempt + 1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve weather data.", 500
            sleep(0.5)

    timezone_str = weather_data.get("timezone", "UTC")
    utc_offset_seconds = weather_data.get("utc_offset_seconds", 0)

    utc_now = datetime.utcnow()

    try:
        target_timezone = pytz.timezone(timezone_str)
        local_time = utc_now.replace(tzinfo=pytz.utc).astimezone(target_timezone)
    except pytz.UnknownTimeZoneError:
        local_time = utc_now + timedelta(seconds=utc_offset_seconds)
    
    datentime = local_time.strftime("%Y-%m-%d %I:%M:%S %p")

    current_weather_data = weather_data.get("current_weather", {})
    current_temp = current_weather_data.get("temperature", 23)
    current_weather_code = current_weather_data.get("weathercode", 0)

    is_day_current = True
    if "daily" in weather_data and weather_data["daily"]["time"]:
        today_index = weather_data["daily"]["time"].index(local_time.strftime("%Y-%m-%d")) if local_time.strftime("%Y-%m-%d") in weather_data["daily"]["time"] else 0
        sunrise_str = weather_data["daily"]["sunrise"][today_index]
        sunset_str = weather_data["daily"]["sunset"][today_index]
        try:
            sunrise_time = datetime.fromisoformat(sunrise_str).astimezone(target_timezone).time()
            sunset_time = datetime.fromisoformat(sunset_str).astimezone(target_timezone).time()
            is_day_current = sunrise_time <= local_time.time() <= sunset_time
        except ValueError:
            is_day_current = 6 <= local_time.hour < 18


    current_icon, current_text = weather.helpers.get_weather_condition(current_weather_code, is_day_current)

    current = {
        "temp": int(current_temp),
        "condition": {"icon": current_icon, "text": current_text}
    }

    days = []
    daily_data = weather_data.get("daily", {})
    if daily_data:
        for i in range(5):
            date_str = daily_data["time"][i]
            high_temp = daily_data["temperature_2m_max"][i]
            low_temp = daily_data["temperature_2m_min"][i]
            wind_speed = daily_data["windspeed_10m_max"][i]
            wind_direction_degrees = daily_data["winddirection_10m_dominant"][i]
            uvi = daily_data["uv_index_max"][i]
            daily_weather_code = daily_data["weathercode"][i]
            sunrise_daily_str = daily_data["sunrise"][i]
            sunset_daily_str = daily_data["sunset"][i]

            forecast_date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            
            is_day_daily = True

            daily_icon, daily_text = weather.helpers.get_weather_condition(daily_weather_code, is_day_daily)

            day_name = forecast_date_obj.strftime("%a")

            days.append({
                "name": day_name,
                "date": date_str,
                "condition": {"icon": daily_icon, "text": daily_text},
                "temp": {"high": int(high_temp), "low": int(low_temp)},
                "wind": {
                    "direction": {"degrees": int(wind_direction_degrees), "compass": weather.helpers.get_compass_direction(wind_direction_degrees)},
                    "speed": int(wind_speed)
                },
                "uvi": int(uvi)
            })

    response_xml = render_template("weather.xml", city=city, country=country, datentime=datentime, current=current, days=days)
    response = Response(response_xml, mimetype="application/xml; charset=utf-8")
    return response

@app.route("/getstaticweather", methods=["GET"])
@app.route("/forecast-data_v3.asp", methods=["GET"])
@app.route("/widget/htc/forecast-data_v3.asp", methods=["GET"])
def getstaticweather():
    locationCode = request.args.get("locCode", "ASI|TW|TW018|TAIPEI")
    continent, country_code, state_code, city_name_short = locationCode.split("|")

    nominatim_search_url = f"https://nominatim.openstreetmap.org/search?q={city_name_short},{country_code}&format=json&limit=1&addressdetails=1"
    headers = {'User-Agent': 'HTC HTTP Service'}
    
    nominatim_data = {}
    lat = 0.0
    lon = 0.0
    city = city_name_short
    country = country_code

    for attempt in range(3):
        try:
            nominatim_response = requests.get(nominatim_search_url, headers=headers, timeout=5)
            nominatim_response.raise_for_status()
            nominatim_data_list = nominatim_response.json()
            if nominatim_data_list:
                nominatim_data = nominatim_data_list[0]
                lat = float(nominatim_data.get("lat", "0.0"))
                lon = float(nominatim_data.get("lon", "0.0"))
                city = nominatim_data.get("address", {}).get("city", nominatim_data.get("address", {}).get("town", nominatim_data.get("address", {}).get("village", city_name_short)))
                country = nominatim_data.get("address", {}).get("country", country_code)
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Nominatim API call failed (attempt {attempt + 1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve location data.", 500
            sleep(0.5)

    open_meteo_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true&forecast_days=5&"
        f"daily=temperature_2m_max,temperature_2m_min,windspeed_10m_max,winddirection_10m_dominant,uv_index_max,weathercode,sunrise,sunset&"
        f"hourly=temperature_2m,windspeed_10m,winddirection_10m,weathercode&"
        f"timezone=auto"
    )
    
    weather_data = {}
    for attempt in range(3):
        try:
            weather_response = requests.get(open_meteo_url, timeout=5)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            break
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"Open-Meteo API call failed (attempt {attempt + 1}/3): {e}")
            if attempt == 2:
                return "Error: Could not retrieve weather data.", 500
            sleep(0.5)

    timezone_str = weather_data.get("timezone", "UTC")
    utc_offset_seconds = weather_data.get("utc_offset_seconds", 0)
    
    utc_now = datetime.utcnow()

    try:
        target_timezone = pytz.timezone(timezone_str)
        local_time = utc_now.replace(tzinfo=pytz.utc).astimezone(target_timezone)
    except pytz.UnknownTimeZoneError:
        local_time = utc_now + timedelta(seconds=utc_offset_seconds)
    
    datentime = local_time.strftime("%Y-%m-%d %I:%M:%S %p")

    current_weather_data = weather_data.get("current_weather", {})
    current_temp = current_weather_data.get("temperature", 23)
    current_weather_code = current_weather_data.get("weathercode", 0)

    is_day_current = True
    if "daily" in weather_data and weather_data["daily"]["time"]:
        today_index = weather_data["daily"]["time"].index(local_time.strftime("%Y-%m-%d")) if local_time.strftime("%Y-%m-%d") in weather_data["daily"]["time"] else 0
        sunrise_str = weather_data["daily"]["sunrise"][today_index]
        sunset_str = weather_data["daily"]["sunset"][today_index]

        try:
            sunrise_time = datetime.fromisoformat(sunrise_str).astimezone(target_timezone).time()
            sunset_time = datetime.fromisoformat(sunset_str).astimezone(target_timezone).time()
            is_day_current = sunrise_time <= local_time.time() <= sunset_time
        except ValueError:
            is_day_current = 6 <= local_time.hour < 18

    current_icon, current_text = weather.helpers.get_weather_condition(current_weather_code, is_day_current)

    current = {
        "temp": int(current_temp),
        "condition": {"icon": current_icon, "text": current_text}
    }

    days = []
    daily_data = weather_data.get("daily", {})
    if daily_data:
        for i in range(5):
            date_str = daily_data["time"][i]
            high_temp = daily_data["temperature_2m_max"][i]
            low_temp = daily_data["temperature_2m_min"][i]
            wind_speed = daily_data["windspeed_10m_max"][i]
            wind_direction_degrees = daily_data["winddirection_10m_dominant"][i]
            uvi = daily_data["uv_index_max"][i]
            daily_weather_code = daily_data["weathercode"][i]
            sunrise_daily_str = daily_data["sunrise"][i]
            sunset_daily_str = daily_data["sunset"][i]

            is_day_daily = True

            daily_icon, daily_text = weather.helpers.get_weather_condition(daily_weather_code, is_day_daily)

            forecast_date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = forecast_date_obj.strftime("%a")

            days.append({
                "name": day_name,
                "date": date_str,
                "condition": {"icon": daily_icon, "text": daily_text},
                "temp": {"high": int(high_temp), "low": int(low_temp)},
                "wind": {
                    "direction": {"degrees": int(wind_direction_degrees), "compass": weather.helpers.get_compass_direction(wind_direction_degrees)},
                    "speed": int(wind_speed)
                },
                "uvi": int(uvi)
            })

    response_xml = render_template("weather.xml", city=city, country=country, datentime=datentime, current=current, days=days)
    response = Response(response_xml, mimetype="application/xml; charset=utf-8")
    return response