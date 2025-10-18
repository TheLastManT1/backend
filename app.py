from config import app, HOST, PORT
from config import WEATHER_ENABLED, STOCKS_ENABLED, YOUTUBE_ENABLED
import helpers
if WEATHER_ENABLED:
    from weather.routes import *
    from weather.weatherSenseV3 import *
if STOCKS_ENABLED: from stocks.routes import *
if YOUTUBE_ENABLED: from youtube.routes import *

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
