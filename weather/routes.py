from config import app
import weather.helpers
from flask import render_template, request, Response
from datetime import datetime, timedelta
import requests
import json
from time import sleep

@app.route("/getweather", methods=["GET"])
@app.route("/lat-lon-search.asp", methods=["GET"])
@app.route("/widget/htc/lat-lon-search.asp", methods=["GET"])
def getweather():
    lat = float(request.args.get("lat", "0"))
    lon = float(request.args.get("lon", "0"))

    nominatim_data = weather.helpers.get_nominatim_reverse(lat, lon)
    if nominatim_data is None:
        return "Error: Could not retrieve location data.", 500

    city = nominatim_data.get("address", {}).get("city", nominatim_data.get("address", {}).get("town", nominatim_data.get("address", {}).get("village", "Unknown City")))
    country = nominatim_data.get("address", {}).get("country", "Unknown Country")

    weather_data = weather.helpers.fetch_open_meteo(lat, lon, forecast_days=5)
    if weather_data is None:
        return "Error: Could not retrieve weather data.", 500

    utc_offset_seconds = weather_data.get("utc_offset_seconds", 0)

    now = datetime.now()
    local_time = now + timedelta(seconds=utc_offset_seconds)
    datentime = local_time.strftime("%Y-%m-%d %I:%M:%S %p")

    current_weather_data = weather_data.get("current_weather", {})
    current_temp = current_weather_data.get("temperature", 23)
    current_weather_code = current_weather_data.get("weathercode", 0)
    is_day_current = bool(current_weather_data.get("is_day", 1))
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
@app.route("/widget/htc2/weather-data.asp", methods=["GET"])
def getstaticweather():
    locationCode = request.args.get("locCode", "ASI|TW|TW018|TAIPEI")
    metric = int(request.args.get("metric", "-1"))
    try:
        continent, country_code, state_code, city_name_short = locationCode.split("|")
    except Exception:
        return "Bad location format", 400

    nominatim_data = weather.helpers.search_nominatim(city_name_short, country_code)
    lat = 0.0
    lon = 0.0
    city = city_name_short
    country = country_code
    if nominatim_data:
        lat = float(nominatim_data.get("lat", "0.0"))
        lon = float(nominatim_data.get("lon", "0.0"))
        city = nominatim_data.get("address", {}).get("city", nominatim_data.get("address", {}).get("town", nominatim_data.get("address", {}).get("village", city_name_short)))
        country = nominatim_data.get("address", {}).get("country", country_code)

    weather_data = weather.helpers.fetch_open_meteo(lat, lon, forecast_days=9)
    if weather_data is None:
        return "Error: Could not retrieve weather data.", 500

    if "htc2" in (request.endpoint or ""):
        use_metric = (metric == 1)

        units = {
            "temp": "C" if use_metric else "F",
            "dist": "KM" if use_metric else "MI",
            "speed": "KM/H" if use_metric else "MPH",
            "pres": "MB" if use_metric else "IN",
            "prec": "MM" if use_metric else "IN"
        }

        tz_name = weather_data.get("timezone", "UTC")
        timeInfo = weather.helpers.get_timezone_info(tz_name)

        local = {
            "city": city,
            "adminArea": {"code": state_code, "name": state_code},
            "country": {"code": country_code, "name": country},
            "lat": f"{lat:.5f}",
            "lon": f"{lon:.5f}",
            "time": weather_data.get("current_weather", {}).get("time", "00:00")[-5:],
            "timeZone": int(timeInfo["timeZone"]),
            "obsDaylight": weather_data.get("current_weather", {}).get("is_day", 1),
            "currentGmtOffset": int(timeInfo["currentGmtOffset"]),
            "timeZoneAbbreviation": timeInfo["timeZoneAbbreviation"]
        }

        cw = weather_data.get("current_weather", {})
        weatherInfo = weather.helpers.get_weather_condition(cw.get("weathercode", 0), bool(cw.get("is_day", 1)))

        currentconditions = {
            "daylight": "True" if cw.get("is_day", 1) else "False",
            "url": "",
            "observationtime": weather.helpers.to_12h_format(local["time"]),
            "pressure": {"value": "", "state": "UNKNOWN"},
            "temperature": round(weather.helpers.convert_temperature(cw.get("temperature", 0), use_metric)),
            "realfeel": "",
            "humidity": "",
            "weathertext": weatherInfo[1],
            "weathericon": weatherInfo[0],
            "windgusts": round(weather.helpers.convert_speed(cw.get("windspeed", 0), use_metric)),
            "windspeed": round(weather.helpers.convert_speed(cw.get("windspeed", 0), use_metric)),
            "winddirection": weather.helpers.get_compass_direction(cw.get("winddirection", 0)),
            "visibility": "",
            "precip": weather_data.get("hourly", {}).get("precipitation", [0])[0],
            "uvindex": {"index": round(weather_data.get("daily", {}).get("uv_index_max", [0])[0]), "text": weather.helpers.uv_index_to_text(weather_data.get("daily", {}).get("uv_index_max", [0])[0])},
            "dewpoint": "",
            "cloudcover": "",
            "apparenttemp": round(weather.helpers.convert_temperature(cw.get("temperature", 0), use_metric)),
            "windchill": round(weather.helpers.convert_temperature(cw.get("temperature", 0), use_metric))
        }

        planets = {}
        for p in ["sun","moon","mercury","venus","mars","jupiter","saturn","uranus","neptune","pluto"]:
            planets[p] = {"sunrise": weather_data.get("daily", {}).get("sunrise", [""])[0][-5:], "sunset": weather_data.get("daily", {}).get("sunset", [""])[0][-5:]}

        moon = []
        start_date = datetime.today()
        for i in range(32):
            d = (start_date + timedelta(days=i)).strftime("%m/%d/%Y")
            moon.append({"date": d, "text": "", "age": (i % 29) + 1})

        forecast_days = []
        daily = weather_data.get("daily", {})
        for i in range(min(9, len(daily.get("time", [])))):
            date = daily.get("time", [""])[i]
            sunrise = daily.get("sunrise", [""])[i][-5:]
            sunset = daily.get("sunset", [""])[i][-5:]
            weathercode = daily.get("weathercode", [0])[i]
            tempMax = daily.get("temperature_2m_max", [0])[i]
            tempMin = daily.get("temperature_2m_min", [0])[i]
            windspeed = daily.get("windspeed_10m_max", [0])[i]
            winddirection = daily.get("winddirection_10m_dominant", [0])[i]
            maxuv = daily.get("uv_index_max", [0])[i]

            day_icon, day_text = weather.helpers.get_weather_condition(weathercode, True)
            night_icon, night_text = weather.helpers.get_weather_condition(weathercode, False)

            forecast_days.append({
                "number": i,
                "url": "",
                "obsdate": date,
                "daycode": weathercode,
                "sunrise": sunrise,
                "sunset": sunset,
                "day_txtshort": day_text,
                "day_txtlong": day_text,
                "day_icon": day_icon,
                "day_high": round(weather.helpers.convert_temperature(tempMax, use_metric)),
                "day_low": round(weather.helpers.convert_temperature(tempMin, use_metric)),
                "day_realfeelhigh": "",
                "day_realfeellow": "",
                "day_windspeed": round(weather.helpers.convert_speed(windspeed, use_metric)),
                "day_winddirection": weather.helpers.get_compass_direction(winddirection),
                "day_windgust": "",
                "day_maxuv": round(maxuv),
                "day_rain": "0.00",
                "day_snow": "0.00",
                "day_ice": "0.00",
                "day_precip": "0.00",
                "day_tstormprob": "0",
                "night_txtshort": night_text,
                "night_txtlong": night_text,
                "night_icon": night_icon,
                "night_high": round(weather.helpers.convert_temperature(tempMax, use_metric)),
                "night_low": round(weather.helpers.convert_temperature(tempMin, use_metric)),
                "night_realfeelhigh": round(weather.helpers.convert_temperature(tempMax, use_metric)),
                "night_realfeellow": round(weather.helpers.convert_temperature(tempMin, use_metric)),
                "night_windspeed": round(weather.helpers.convert_speed(windspeed, use_metric)),
                "night_winddirection": weather.helpers.get_compass_direction(winddirection),
                "night_windgust": round(weather.helpers.convert_speed(windspeed, use_metric) * 1.6),  # this is a rough estimation
                "night_maxuv": round(maxuv),
                "night_rain": "0.00",
                "night_snow": "0.00",
                "night_ice": "0.00",
                "night_precip": "0.00",
                "night_tstormprob": "0"
            })

        forecast_hours = []
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        precs = hourly.get("precipitation", [])
        ws = hourly.get("windspeed_10m", [])
        wdirs = hourly.get("winddirection_10m", [])
        wcodes = hourly.get("weathercode", [])

        for i in range(min(24, len(times))):
            t = times[i][-5:]
            forecast_hours.append({
                "time": t,
                "icon": weather.helpers.get_weather_condition(wcodes[i] if i < len(wcodes) else 0, True)[0] if wcodes else 0,
                "temp": round(weather.helpers.convert_temperature(temps[i] if i < len(temps) else 0, use_metric)),
                "realfeel": "",
                "precip": precs[i] if i < len(precs) else 0,
                "windspeed": round(weather.helpers.convert_speed(ws[i] if i < len(ws) else 0, use_metric)),
                "winddirection": weather.helpers.get_compass_direction(wdirs[i] if i < len(wdirs) else 0),
                "text": weather.helpers.get_weather_condition(wcodes[i] if i < len(wcodes) else 0, True)[1] if wcodes else "",
                "obsdate": times[i][:10],
                "mobileLink": ""
            })

        if len(forecast_hours) == 24:
            forecast_hours = forecast_hours[13:] + forecast_hours[:13]

        template_context = {
            "units": units,
            "local": local,
            "currentconditions": currentconditions,
            "planets": planets,
            "moon": moon,
            "forecast_url": "",
            "forecast_days": forecast_days,
            "forecast_hours": forecast_hours,
            "product": "htc2 feed",
            "copyright_year": datetime.now().year
        }

        response_xml = render_template("weatherV3.xml", **template_context)
        return Response(response_xml, mimetype="application/xml; charset=utf-8")
    else:
        utc_offset_seconds = weather_data.get("utc_offset_seconds", 0)
        now = datetime.now()
        local_time = now + timedelta(seconds=utc_offset_seconds)
        datentime = local_time.strftime("%Y-%m-%d %I:%M:%S %p")

        current_weather_data = weather_data.get("current_weather", {})
        current_temp = current_weather_data.get("temperature", 23)
        current_weather_code = current_weather_data.get("weathercode", 0)
        is_day_current = bool(current_weather_data.get("is_day", 1))
        current_icon, current_text = weather.helpers.get_weather_condition(current_weather_code, is_day_current)

        current = {
            "temp": int(current_temp),
            "condition": {"icon": current_icon, "text": current_text}
        }

        days = []
        daily_data = weather_data.get("daily", {})
        if daily_data:
            for i in range(min(5, len(daily_data.get("time", [])))):
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
                day_name = forecast_date_obj.strftime("%a")

                is_day_daily = True

                daily_icon, daily_text = weather.helpers.get_weather_condition(daily_weather_code, is_day_daily)

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