import os
import uuid
import time
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from yt_dlp import YoutubeDL

# -----------------------------
# Setup
# -----------------------------
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="yt-dlp FastAPI Backend (with URL normalize)")


# -----------------------------
# Helpers
# -----------------------------
def normalize_youtube_url(url: str) -> str:
    """
    YouTube URL ko clean/normalize kare:
    - youtu.be/dQw4w9WgXcQ?si=...  -> https://www.youtube.com/watch?v=dQw4w9WgXcQ
    - https://www.youtube.com/watch?v=ID&ab_channel=... -> same clean watch URL
    - https://www.youtube.com/shorts/ID?si=... -> https://www.youtube.com/watch?v=ID
    Agar YouTube URL nahi hai, original url return kare.
    """
    url = url.strip()
    if not url:
        return url

    parsed = urlparse(url)
    if not parsed.netloc:
        # Could be plain ID or invalid, just return as-is
        return url

    host = parsed.netloc.lower()
    video_id = None

    if "youtu.be" in host:
        # Short URL: path is "/VIDEO_ID"
        video_id = parsed.path.lstrip("/")
    elif "youtube.com" in host:
        # Normal YouTube URLs
        # Try ?v=ID
        qs = parse_qs(parsed.query)
        video_id = qs.get("v", [None])[0]

        # Shorts: /shorts/VIDEO_ID
        if not video_id and parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/")[1].split("/")[0]

    # If we detected a video id, build clean watch URL
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    # Fallback: return original
    return url


def build_ydl_opts(media_type: str) -> dict:
    """
    yt-dlp options safe for public servers (no cookies).
    """
    base_opts = {
        "noplaylist": True,
        "quiet": True,
        # Fix JS runtime warning by forcing default client
        "extractor_args": {"youtube": {"player_client": ["default"]}},
    }

    if media_type == "audio":
        base_opts["format"] = "bestaudio/best"
    else:
        base_opts["format"] = "bestvideo[height<=720]+bestaudio/best/best[height<=720]"

    return base_opts


def download_with_ytdlp(url: str, media_type: str):
    start = time.time()
    ydl_opts = build_ydl_opts(media_type)

    # Unique filename
    unique_id = str(uuid.uuid4())[:8]
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_DIR, f"{unique_id}-%(title)s.%(ext)s")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

    except Exception as e:
        msg = str(e)

        # YouTube is blocking the server IP with CAPTCHA / sign-in check
        if "Sign in to confirm" in msg or "confirm you’re not a bot" in msg:
            raise HTTPException(
                status_code=403,
                detail=(
                    "This video cannot be downloaded from this server because "
                    "YouTube requires sign-in/CAPTCHA for it. Try another video URL."
                ),
            )

        print("yt-dlp error:", repr(e))
        raise HTTPException(status_code=400, detail=f"yt-dlp error: {msg}")

    # Resolve filepath safely
    filepath = None
    if isinstance(info, dict):
        if "requested_downloads" in info and info.get("requested_downloads"):
            filepath = info["requested_downloads"][0].get("filepath")
        elif "filepath" in info:
            filepath = info["filepath"]

    elapsed = time.time() - start

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=500,
            detail="Download finished but output file not found.",
        )

    print(f"[yt-dlp] Downloaded in {elapsed:.2f}s → {filepath}")
    return filepath, elapsed


# -----------------------------
# API ROUTES
# -----------------------------
@app.get("/api/download")
async def api_download(
    url: str = Query(..., description="YouTube URL (any format)"),
    type: str = Query("video", description="audio or video"),
    show_time: bool = Query(
        False,
        description="If true, return HTML page with processing time",
    ),
):
    raw_url = url.strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Clean/normalize YouTube URLs like:
    # https://youtu.be/dQw4w9WgXcQ?si=...
    # https://youtube.com/shorts/ID?si=...
    url = normalize_youtube_url(raw_url)

    media_type = "audio" if type.lower() == "audio" else "video"

    filepath, elapsed = download_with_ytdlp(url, media_type)
    filename = os.path.basename(filepath)

    # Show processing time page + auto download
    if show_time:
        html = f"""
        <!doctype html>
        <html>
        <head><meta charset="utf-8"><title>Processing Time</title></head>
        <body style="font-family:sans-serif;">
            <h2>Download complete ✅</h2>
            <p><b>Processing time:</b> {elapsed:.2f} seconds</p>
            <p><b>File:</b> {filename}</p>
            <p>If download didn't start, <a href="/file/{filename}" download>click here</a>.</p>
            <iframe src="/file/{filename}" style="display:none;"></iframe>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    # Direct file download
    return FileResponse(
        filepath,
        filename=filename,
        media_type="application/octet-stream",
        headers={"X-Processing-Time": f"{elapsed:.3f}s"},
    )


@app.get("/file/{filename}")
async def get_file(filename: str):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename)


@app.get("/")
async def root():
    return {
        "status": "OK",
        "message": "yt-dlp backend running",
        "example_short_link": "/api/download?url=https://youtu.be/dQw4w9WgXcQ?si=k9cNBXqkRxPYgJsV&type=video&show_time=true",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
