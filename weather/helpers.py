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