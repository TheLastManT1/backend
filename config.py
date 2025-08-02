from flask import Flask
import googleapiclient.discovery

app = Flask(__name__)

HOST = "IP_ADDRESS_HERE"
PORT = 6571

WEATHER_ENABLED = True
STOCKS_ENABLED = True
YOUTUBE_ENABLED = True

# YouTube configuration
YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY_HERE"
VIDEO_LIFETIME = 3 # in days
CLEANUP_INTERVAL = 1 # in hours

# Optional: Enable proxy support if behind a reverse proxy
# from werkzeug.middleware.proxy_fix import ProxyFix
# app.wsgi_app = ProxyFix(
#     app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
# )