from config import app, YOUTUBE_API_KEY, CLEANUP_INTERVAL
from config import HOST, PORT
import youtube.helpers
import os
from flask import render_template, request, Response, send_from_directory
from datetime import datetime, timezone
import atexit
import concurrent.futures
import threading
import time
import uuid
import hashlib
import random
import html
import re
from googleapiclient.discovery import build

_thread_local = threading.local()

def _yt_client():
    if not hasattr(_thread_local, 'youtube_client'):
        _thread_local.youtube_client = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    return _thread_local.youtube_client

def yt_client():
    return _yt_client()

# Device registration store (better solution needed if scaling)
registered_devices = {}
device_lock = threading.Lock()

with app.app_context():
    if not os.path.exists(youtube.helpers.STATIC_DIR):
        os.makedirs(youtube.helpers.STATIC_DIR, exist_ok=True)
    if not os.path.exists(youtube.helpers.THUMBNAILS_DIR):
        os.makedirs(youtube.helpers.THUMBNAILS_DIR, exist_ok=True)
    youtube.helpers.cleanup_files()
    youtube.helpers.periodic_cleanup(CLEANUP_INTERVAL * 60 * 60)

@app.route("/youtube/accounts/registerDevice", methods=["POST"])
@app.route("/registerDevice", methods=["POST"])
def reg_device():
    try:
        device_id = ""
        while len(device_id) != 7:
            device_id += "qwertyuiopasdfghjklzxcvbnm1234567890"[random.randint(0, 35)]
        while device_id in registered_devices:
            device_id = ""
            while len(device_id) != 7:
                device_id += "qwertyuiopasdfghjklzxcvbnm1234567890"[random.randint(0, 35)]
        device_data = {
            "device_id": device_id,
            "registered_at": int(time.time()),
            "user_agent": request.headers.get("User-Agent", ""),
            "ip_address": request.remote_addr
        }
        with device_lock:
            registered_devices[device_id] = device_data
        response_text = f"DeviceId={device_id}\nDeviceKey=ULxlVAAVMhZ2GeqZA/X1GgqEEIP1ibcd3S+42pkWfmk="
        response = Response(response_text, mimetype='text/plain')
        return response
    except Exception as e:
        print(f"Device registration failed: {e}")
        return Response("Error: Registration failed", status=500, mimetype='text/plain')

@app.route("/schemas/2007/categories.cat", methods=["GET"])
def categories():
    return Response(render_template("ytcategories.cat"), mimetype="application/atom+xml")

@app.route("/static/thumbnails/<filename>")
def thumbnail(filename):
    if not filename.endswith(".png"):
        filename += ".png"
    return send_from_directory(youtube.helpers.THUMBNAILS_DIR, filename)

@app.route("/static/videos/<filename>")
def video(filename):
    return send_from_directory(youtube.helpers.STATIC_DIR, filename)

@app.route("/feeds/api/videos/<video_id>/related")
def related(video_id):
    start_index = int(request.args.get("start-index", "1"))
    max_results = min(int(request.args.get("max-results", "8")), 25)
    try:
        youtube_client = yt_client()
        original_video = youtube_client.videos().list(part="snippet", id=video_id).execute()
        if not original_video.get("items"):
            return create_empty_related_feed(video_id, start_index)
        video_snippet = original_video["items"][0]["snippet"]
        search_terms = video_snippet["title"]
        search_response = youtube_client.search().list(
            part="snippet",
            q=search_terms,
            type="video",
            maxResults=max_results,
            safeSearch="none",
            order="relevance"
        ).execute()
        if not search_response.get("items"):
            return create_empty_related_feed(video_id, start_index)
        video_ids = [item["id"]["videoId"] for item in search_response["items"] if item["id"]["videoId"] != video_id]
        if not video_ids:
            return create_empty_related_feed(video_id, start_index)
        videos_response = youtube_client.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(video_ids[:max_results])
        ).execute()
        videos = videos_response.get("items", [])
        processed_videos = []
        host_url = f"http://{HOST}:{PORT}"
        def process_related_video(video_data, host):
            try:
                mp4_url, threegp_url, yt_thumb_url = youtube.helpers.video_with_thumb(video_data)
                # Save thumbnail locally and use local path
                from youtube.helpers import save_thumbnail
                video_id = video_data.get("id")
                local_thumb_url = None
                if yt_thumb_url and video_id:
                    local_thumb_url = save_thumbnail(video_id, yt_thumb_url)
                video_data["contentDetails"]["videoLocation"] = {
                    "mp4": host + mp4_url,
                    "3gp": host + threegp_url
                }
                if local_thumb_url:
                    video_data["snippet"]["thumbnailUrl"] = host + local_thumb_url
                return video_data
            except Exception as e:
                print(f"Failed to process related video: {e}")
                return None
        max_workers = min(3, len(videos))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(process_related_video, video, host_url): video for video in videos
            }
            for future in concurrent.futures.as_completed(future_to_video, timeout=180):
                try:
                    result = future.result()
                    if result is not None:
                        processed_videos.append(result)
                except Exception as e:
                    continue
        response_data = {
            "pageInfo": {
                "totalResults": len(processed_videos),
                "startIndex": start_index,
                "resultsPerPage": len(processed_videos)
            }
        }
        response = render_template(
            "ytvideos",
            host=f"{HOST}:{PORT}",
            updated=datetime.now(timezone.utc),
            title=f"Related to {video_snippet['title']}",
            info=response_data["pageInfo"],
            results=processed_videos
        )
        return Response(response, mimetype="application/atom+xml")
    except Exception as e:
        print(f"Related videos endpoint failed: {e}")
        return create_empty_related_feed(video_id, start_index)

@app.route("/feeds/api/users/<username>")
def user(username):
    try:
        youtube_client = yt_client()
        
        # Search for channel by name or handle
        search_response = youtube_client.search().list(
            part="snippet",
            q=username,
            type="channel",
            maxResults=1
        ).execute()
        
        if not search_response.get("items"):
            return create_empty_user_feed(username)
        
        channel_id = search_response["items"][0]["snippet"]["channelId"]

        channel_response = youtube_client.channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id
        ).execute()
        
        if not channel_response.get("items"):
            return create_empty_user_feed(username)
        
        channel_data = channel_response["items"][0]

        response_xml = render_template(
            "ytuser",
            host=f"{HOST}:{PORT}",
            username=username,
            published=channel_data['snippet']['publishedAt'],
            updated=datetime.now(timezone.utc).isoformat() + "Z",
            title=channel_data['snippet']['title'],
            description=channel_data['snippet'].get('description', ''),
            country=channel_data['snippet'].get('country', ''),
            subscriberCount=channel_data['statistics'].get('subscriberCount', '0'),
            viewCount=channel_data['statistics'].get('viewCount', '0'),
            notfound=False
        )
        response = Response(response_xml, mimetype='application/atom+xml')
        response.headers.set("Cache-Control", "public, max-age=3600")
        return response
    except Exception as e:
        print(f"User profile endpoint failed for {username}: {e}")
        return create_empty_user_feed(username)

@app.route("/feeds/api/users/<username>/uploads")
def uploads(username):
    start_index = int(request.args.get("start-index", "1"))
    max_results = min(int(request.args.get("max-results", "3")), 25)
    try:
        youtube_client = yt_client()
        
        # Search for channel by name or handle
        search_response = youtube_client.search().list(
            part="snippet",
            q=username,
            type="channel",
            maxResults=1
        ).execute()
        
        if not search_response.get("items"):
            return create_empty_uploads_feed(username, start_index)
        
        channel_id = search_response["items"][0]["snippet"]["channelId"]
        
        channel_response = youtube_client.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()
        
        if not channel_response.get("items"):
            return create_empty_uploads_feed(username, start_index)
        
        uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        playlist_response = youtube_client.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results
        ).execute()
        
        if not playlist_response.get("items"):
            return create_empty_uploads_feed(username, start_index)
        
        video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_response["items"]]
        
        videos_response = youtube_client.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(video_ids)
        ).execute()
        
        videos = videos_response.get("items", [])
        processed_videos = []
        host_url = f"http://{HOST}:{PORT}"
        
        def process_upload_video(video_data, host):
            try:
                mp4_url, threegp_url, yt_thumb_url = youtube.helpers.video_with_thumb(video_data)
                from youtube.helpers import save_thumbnail
                video_id = video_data.get("id")
                local_thumb_url = None
                if yt_thumb_url and video_id:
                    local_thumb_url = save_thumbnail(video_id, yt_thumb_url)
                video_data["contentDetails"]["videoLocation"] = {
                    "mp4": host + mp4_url,
                    "3gp": host + threegp_url
                }
                if local_thumb_url:
                    video_data["snippet"]["thumbnailUrl"] = host + local_thumb_url
                return video_data
            except Exception as e:
                print(f"Failed to process upload video: {e}")
                return None
        
        max_workers = min(3, len(videos))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(process_upload_video, video, host_url): video for video in videos
            }
            
            for future in concurrent.futures.as_completed(future_to_video, timeout=180):
                try:
                    result = future.result()
                    if result is not None:
                        processed_videos.append(result)
                except Exception as e:
                    print(f"Upload video processing exception: {e}")
                    continue
        
        response_data = {
            "pageInfo": {
                "totalResults": len(processed_videos),
                "startIndex": start_index,
                "resultsPerPage": len(processed_videos)
            }
        }
        
        response = render_template(
            "ytvideos",
            host=f"{HOST}:{PORT}",
            updated=datetime.now(timezone.utc),
            title=f"Uploads by {username}",
            info=response_data["pageInfo"],
            results=processed_videos
        )
        return Response(response, mimetype="application/atom+xml")

    except Exception as e:
        print(f"User uploads endpoint failed for {username}: {e}")
        return create_empty_uploads_feed(username, start_index)
        

@app.route("/feeds/api/videos")
def search():
    query = request.args.get("vq", "")
    start_index = int(request.args.get("start-index", "1"))
    max_results = min(int(request.args.get("max-results", "10")), 25)
    orderby = request.args.get("orderby", "relevance")
    client = request.args.get("client", "")
    if not query:
        return create_empty_search_feed("", start_index)
    try:
        youtube_client = yt_client()
        
        # Map orderby parameter to YouTube API order (in case of alternative names)
        order_mapping = {
            "relevance": "relevance",
            "published": "date",
            "viewCount": "viewCount",
            "rating": "rating"
        }
        youtube_order = order_mapping.get(orderby, "relevance")
        
        search_response = youtube_client.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            order=youtube_order,
            safeSearch="none"
        ).execute()
        
        if not search_response.get("items"):
            return create_empty_search_feed(query, start_index)
        
        video_ids = [item["id"]["videoId"] for item in search_response["items"]]
        
        videos_response = youtube_client.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=",".join(video_ids)
        ).execute()
        
        videos = videos_response.get("items", [])
        processed_videos = []
        host_url = f"http://{HOST}:{PORT}"
        
        def process_search_video(video_data, host):
            try:
                mp4_url, threegp_url, yt_thumb_url = youtube.helpers.video_with_thumb(video_data)
                from youtube.helpers import save_thumbnail
                video_id = video_data.get("id")
                local_thumb_url = None
                if yt_thumb_url and video_id:
                    local_thumb_url = save_thumbnail(video_id, yt_thumb_url)
                video_data["contentDetails"]["videoLocation"] = {
                    "mp4": host + mp4_url,
                    "3gp": host + threegp_url
                }
                if local_thumb_url:
                    video_data["snippet"]["thumbnailUrl"] = host + local_thumb_url
                return video_data
            except Exception as e:
                print(f"Failed to process search video: {e}")
                return None
        
        max_workers = min(5, len(videos))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_video = {
                executor.submit(process_search_video, video, host_url): video for video in videos
            }
            
            for future in concurrent.futures.as_completed(future_to_video, timeout=300):
                try:
                    result = future.result()
                    if result is not None:
                        processed_videos.append(result)
                except Exception as e:
                    print(f"Search video processing exception: {e}")
                    continue
        
        video_id_order = {v["id"]: i for i, v in enumerate(videos)}
        processed_videos.sort(key=lambda x: video_id_order.get(x["id"], 999))
        
        response_data = {
            "pageInfo": {
                "totalResults": len(processed_videos),
                "startIndex": start_index,
                "resultsPerPage": len(processed_videos)
            }
        }
        
        response = render_template(
            "ytsearch",
            host=f"{HOST}:{PORT}",
            updated=datetime.now(timezone.utc).isoformat() + "Z",
            title=f"Videos matching: {query}",
            query=query,
            orderby=orderby,
            info=response_data["pageInfo"],
            results=processed_videos
        )
        return Response(response, mimetype="application/atom+xml")

    except Exception as e:
        print(f"Video search endpoint failed for '{query}': {e}")
        return create_empty_search_feed(query, start_index)

@app.route("/feeds/api/standardfeeds/<usercountry>/most_viewed")
def trending(usercountry):
    startindex = int(request.args.get("start-index", "1"))
    max_results = min(int(request.args.get("max-results", "10")), 25)
    try:
        youtube_client = yt_client()
        videos_response = youtube_client.videos().list(
            part="snippet,contentDetails,statistics,status",
            chart="mostPopular",
            regionCode=usercountry,
            maxResults=max_results
        ).execute()
        
        if not videos_response.get("items"):
            print("No videos found in API response")
            return create_empty_feed(usercountry, startindex)
        
        videos = videos_response["items"]
        processed_videos = []
        
        host_url = f"http://{HOST}:{PORT}"
        
        def process_video(video_data, host):
            try:
                mp4_url, threegp_url, yt_thumb_url = youtube.helpers.video_with_thumb(video_data)
                from youtube.helpers import save_thumbnail
                video_id = video_data.get("id")
                local_thumb_url = None
                if yt_thumb_url and video_id:
                    local_thumb_url = save_thumbnail(video_id, yt_thumb_url)
                video_data["contentDetails"]["videoLocation"] = {
                    "mp4": host + mp4_url,
                    "3gp": host + threegp_url
                }
                if local_thumb_url:
                    video_data["snippet"]["thumbnailUrl"] = host + local_thumb_url
                return video_data
            except Exception as e:
                print(f"Failed to process video {video_data.get('id', 'unknown')}: {e}")
                return None     
            
        # Use ThreadPoolExecutor for parallel processing
        max_workers = min(5, len(videos))  # Limit concurrent downloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all video processing jobs with host_url parameter
            future_to_video = {
                executor.submit(process_video, video, host_url): video for video in videos
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_video, timeout=300):  # 5 minute timeout
                try:
                    result = future.result()
                    # Only add successful results (filter out None)
                    if result is not None:
                        processed_videos.append(result)
                except concurrent.futures.TimeoutError:
                    continue
                except Exception:
                    continue
        
        # Sort processed videos to maintain original order
        video_id_order = {v["id"]: i for i, v in enumerate(videos)}
        processed_videos.sort(key=lambda x: video_id_order.get(x["id"], 999))
        
        # Update response data
        videos_response["items"] = processed_videos
        videos_response["pageInfo"]["startIndex"] = startindex
        
        response = render_template(
            "ytvideos",
            host=f"{HOST}:{PORT}",
            updated=datetime.now(timezone.utc),
            title="Trending",
            info=videos_response["pageInfo"],
            results=processed_videos
        )
        return Response(response, mimetype="application/atom+xml")

        with open(youtube.helpers.STATIC_DIR + "/trending.log", "w") as log_file:
            log_file.write(response.get_data(as_text=True))

        return response
        
    except Exception as e:
        print(f"Trending endpoint failed: {e}")
        return create_empty_feed(usercountry, startindex)

@app.route("/youtube/download/<video_id>")
def download_video(video_id):
    format = request.args.get("format", "mp4")
    file_url = youtube.helpers.download_video_on_demand(video_id, format)
    if not file_url:
        return Response("Download failed or format not supported", status=404, mimetype="text/plain")
    
    file_path = file_url.lstrip("/")
    if not file_path.startswith("static/videos/"):
        return Response("Invalid file path", status=400, mimetype="text/plain")
    filename = os.path.basename(file_path)
    return send_from_directory("static/videos", filename)

def create_empty_feed(country, start_index):
    empty_info = {
        "totalResults": 0,
        "startIndex": start_index,
        "resultsPerPage": 0
    }
    response_xml = render_template(
        "ytvideos",
        host=f"{HOST}:{PORT}",
        updated=datetime.now(timezone.utc),
        title="Trending",
        info=empty_info,
        results=[]
    )
    response = Response(response_xml, mimetype="application/atom+xml")
    return response

def create_empty_related_feed(video_id, start_index):
    empty_info = {
        "totalResults": 0,
        "startIndex": start_index,
        "resultsPerPage": 0
    }
    response_xml = render_template(
        "ytvideos",
        host=f"{HOST}:{PORT}",
        updated=datetime.now(timezone.utc),
        title=f"Related to {video_id}",
        info=empty_info,
        results=[]
    )
    response = Response(response_xml, mimetype="application/atom+xml")
    return response

def create_empty_user_feed(username):
    response_xml = render_template(
        "ytuser",
        host=f"{HOST}:{PORT}",
        username=username,
        published=datetime.now(timezone.utc).isoformat() + "Z",
        updated=datetime.now(timezone.utc).isoformat() + "Z",
        title=username,
        description="User not found",
        country="",
        subscriberCount="0",
        viewCount="0",
        notfound=True
    )
    return Response(response_xml, status=404, mimetype='application/atom+xml')

def create_empty_uploads_feed(username, start_index):
    empty_info = {
        "totalResults": 0,
        "startIndex": start_index,
        "resultsPerPage": 0
    }
    response_xml = render_template(
        "ytvideos",
        host=f"{HOST}:{PORT}",
        updated=datetime.now(timezone.utc),
        title=f"Uploads by {username}",
        info=empty_info,
        results=[]
    )
    response = Response(response_xml, mimetype="application/atom+xml")
    return response

def create_empty_search_feed(query, start_index):
    empty_info = {
        "totalResults": 0,
        "startIndex": start_index,
        "resultsPerPage": 0
    }
    title = f"Videos matching: {query}" if query else "Videos matching: "
    response_xml = render_template(
        "ytsearch",
        host=f"{HOST}:{PORT}",
        updated=datetime.now(timezone.utc).isoformat() + "Z",
        title=title,
        query=query,
        orderby="relevance",
        info=empty_info,
        results=[]
    )
    response = Response(response_xml, mimetype="application/atom+xml")
    return response
