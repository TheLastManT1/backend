from config import VIDEO_LIFETIME
import requests
import os
import random
import string
import subprocess
import time
import concurrent.futures
import threading
from pathlib import Path
import hashlib
import json
from PIL import Image
import io
import html
import re
from googleapiclient.discovery import build

STATIC_DIR = "static/videos"
THUMBNAILS_DIR = "static/thumbnails"
LIFETIME_SECONDS = VIDEO_LIFETIME * 24 * 60 * 60

_download_cache = {}
_cache_lock = threading.Lock()

_thread_local = threading.local()

# InnerTube API configuration
INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
ANDROID_CLIENT_CONTEXT = {
    "client": {
        "hl": "en",
        "clientName": "ANDROID",
        "clientVersion": "19.02.39",
        "androidSdkVersion": 34,
    }
}
ANDROID_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "user-agent": "com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip",
    "referer": "https://www.youtube.com/"
}

def yt_client():
    if not hasattr(_thread_local, 'youtube_client'):
        from config import YOUTUBE_API_KEY
        _thread_local.youtube_client = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    return _thread_local.youtube_client

def country_by_ip(ip):
    try:
        from urllib.request import urlopen
        import json
        url = f'https://ipinfo.io/{ip}/json'
        res = urlopen(url)
        data = json.load(res)
        return data.get("country", "US")
    except:
        return "US"

def rand_filename(ext):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + f".{ext}"

def cleanup_files(directory=None, max_age_seconds=LIFETIME_SECONDS):
    directories = [directory] if directory else [STATIC_DIR, THUMBNAILS_DIR]
    for dir_path in directories:
        if not os.path.exists(dir_path):
            continue
        now = time.time()
        for fname in os.listdir(dir_path):
            path = os.path.join(dir_path, fname)
            try:
                if os.path.isfile(path):
                    if now - os.path.getmtime(path) > max_age_seconds:
                        os.remove(path)
            except Exception as e:
                print(f"Error deleting file {path}: {e}")

def periodic_cleanup(interval_seconds=3600):
    def run():
        while True:
            try:
                cleanup_files()
            except Exception as e:
                print(f"Periodic cleanup error: {e}")
            time.sleep(interval_seconds)
    t = threading.Thread(target=run, daemon=True)
    t.start()

def cache_key(video_id):
    return hashlib.md5(video_id.encode()).hexdigest()[:12]

def save_thumbnail(video_id, thumbnail_url):
    try:
        os.makedirs(THUMBNAILS_DIR, exist_ok=True)
        thumb_name = f"{cache_key(video_id)}_thumb.png"
        thumb_url_path = f"{cache_key(video_id)}_thumb.png"
        thumb_path = os.path.join(THUMBNAILS_DIR, thumb_name)
        if os.path.exists(thumb_path):
            file_age = time.time() - os.path.getmtime(thumb_path)
            if file_age < LIFETIME_SECONDS:
                return f"/static/thumbnails/{thumb_url_path}"
        response = requests.get(thumbnail_url, timeout=10, stream=True)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        target_width, target_height = 320, 240
        scale_w = target_width / image.width
        scale_h = target_height / image.height
        scale = min(scale_w, scale_h)
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        final_image = Image.new('RGB', (target_width, target_height), color='#efefef')
        x_offset = (target_width - new_width) // 2
        y_offset = (target_height - new_height) // 2
        final_image.paste(image, (x_offset, y_offset))
        final_image.save(thumb_path, 'PNG', optimize=True)
        return f"/static/thumbnails/{thumb_url_path}"
    except Exception as e:
        print(f"Thumbnail download failed for {video_id}: {e}")
        return None

def thumb_url(video_data):
    try:
        thumbnails = video_data.get('snippet', {}).get('thumbnails', {})
        if 'medium' in thumbnails:
            return thumbnails['medium']['url']
        for quality in ['high', 'default']:
            if quality in thumbnails:
                return thumbnails[quality]['url']
        if thumbnails:
            return list(thumbnails.values())[0]['url']
        return None
    except Exception as e:
        print(f"Failed to extract thumbnail URL: {e}")
        return None

def video_data_api(video_id):
    try:
        payload = {
            "context": ANDROID_CLIENT_CONTEXT,
            "playbackContext": {"vis": 0, "lactMilliseconds": "1"},
            "videoId": video_id,
            "racyCheckOk": True,
            "contentCheckOk": True
        }
        response = requests.post(
            INNERTUBE_API_URL,
            headers=ANDROID_HEADERS,
            json=payload,
            timeout=10
        )
        if response.status_code != 200:
            print(f"InnerTube API error: {response.status_code}")
            return None
        data = response.json()
        streaming_data = data.get("streamingData", {})
        if not streaming_data:
            print(f"No streaming data for video {video_id}")
            return None
        return streaming_data
    except Exception as e:
        print(f"InnerTube API request failed for {video_id}: {e}")
        return None

def download_chunk(url, file_path, video_id):
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Direct download failed for {video_id}: {e}")
        return False

def best_format(streaming_data):
    formats = streaming_data.get("formats", [])
    adaptive_formats = streaming_data.get("adaptiveFormats", [])
    for fmt in formats:
        mime_type = fmt.get("mimeType", "")
        height = fmt.get("height", 0)
        if "mp4" in mime_type and height <= 480:
            return fmt.get("url")
    video_formats = [f for f in adaptive_formats if f.get("mimeType", "").startswith("video/mp4")]
    video_formats.sort(key=lambda x: x.get("height", 999))
    for fmt in video_formats:
        height = fmt.get("height", 0)
        if height <= 480:
            return fmt.get("url")
    for fmt in video_formats:
        return fmt.get("url")
    return None

def get_video(video_id):
    key = cache_key(video_id)
    with _cache_lock:
        if key in _download_cache:
            cached_result = _download_cache[key]
            if (os.path.exists(cached_result[0].lstrip('/')) and os.path.exists(cached_result[1].lstrip('/'))):
                return cached_result
            else:
                del _download_cache[key]
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR, exist_ok=True)
    mp4_filename = f"{key}.mp4"
    mp4_path = os.path.join(STATIC_DIR, mp4_filename)
    if os.path.exists(mp4_path):
        result = (f"/{mp4_path}", f"/{mp4_path}")
        with _cache_lock:
            _download_cache[key] = result
        return result
    try:
        streaming_data = video_data_api(video_id)
        if not streaming_data:
            print(f"Failed to get streaming data for {video_id}")
            return None, None
        video_url = best_format(streaming_data)
        if not video_url:
            print(f"No suitable format found for {video_id}")
            return None, None
        if not download_chunk(video_url, mp4_path, video_id):
            print(f"Download failed for {video_id}")
            return None, None
    except Exception as e:
        print(f"Download failed for {video_id}: {e}")
        return None, None
    # 3GP conversion (disabled, enable if needed)
    # threegp_filename = f"{key}.3gp"
    # threegp_path = os.path.join(STATIC_DIR, threegp_filename)
    # try:
    #     subprocess.run([
    #         "ffmpeg", "-y", "-i", mp4_path,
    #         "-vf", "scale=176:144:force_original_aspect_ratio=decrease,pad=176:144:(ow-iw)/2:(oh-ih)/2",
    #         "-c:v", "h263",
    #         "-b:v", "64k",
    #         "-r", "15",
    #         "-c:a", "amr_nb",
    #         "-ar", "8000",
    #         "-b:a", "12.2k",
    #         "-ac", "1",
    #         "-f", "3gp",
    #         threegp_path
    #     ], check=True, capture_output=True, text=True)
    # except subprocess.CalledProcessError as e:
    #     print(f"3GP conversion failed for {video_id}: {e}")
    #     try:
    #         subprocess.run([
    #             "ffmpeg", "-y", "-i", mp4_path,
    #             "-vf", "scale=176:144",
    #             "-c:v", "h263", "-b:v", "64k", "-r", "10",
    #             "-c:a", "aac", "-b:a", "16k", "-ar", "8000", "-ac", "1",
    #             "-f", "3gp", threegp_path
    #         ], check=True, capture_output=True, text=True)
    #     except subprocess.CalledProcessError as e2:
    #         print(f"3GP fallback conversion also failed: {e2}")
    #         return f"/{mp4_path}", f"/{mp4_path}"
    result = (f"/{mp4_path}", f"/{mp4_path}")
    with _cache_lock:
        _download_cache[key] = result
    return result

def video_with_thumb(video_data):
    video_id = video_data.get("id")
    if not video_id:
        return None, None, None
    mp4_url = f"/youtube/download/{video_id}?format=mp4"
    threegp_url = f"/youtube/download/{video_id}?format=3gp"
    thumbnail_url = thumb_url(video_data)
    return mp4_url, threegp_url, thumbnail_url

def download_video_on_demand(video_id, format):
    if format not in ("mp4", "3gp"):
        return None
    mp4_url, threegp_url = get_video(video_id)
    if format == "mp4":
        return mp4_url
    elif format == "3gp":
        return threegp_url