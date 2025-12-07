import os
import uuid
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from yt_dlp import YoutubeDL

# -----------------------------
# Setup
# -----------------------------
DOWNLOAD_DIR = "downloads"
COOKIE_FILE = "cookies.txt"      # <--- ADD YOUR EXPORTED COOKIES HERE
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="yt-dlp Backend API with Cookie Support")


# -----------------------------
# Helper: Download with yt-dlp
# -----------------------------
def download_with_ytdlp(url: str, ydl_opts: dict):
    start = time.time()

    # unique filename
    unique_id = str(uuid.uuid4())[:8]
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_DIR, f"{unique_id}-%(title)s.%(ext)s")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

    except Exception as e:
        # Handle YouTube CAPTCHA / BOT block
        if "Sign in to confirm" in str(e):
            raise HTTPException(
                status_code=403,
                detail="YouTube blocked this video for server IP. Cookies required or expired."
            )

        print("yt-dlp error:", repr(e))
        raise HTTPException(status_code=400, detail=f"yt-dlp error: {e}")

    # Safely detect final file path
    filepath = None
    if "requested_downloads" in info and info["requested_downloads"]:
        filepath = info["requested_downloads"][0].get("filepath")
    elif "filepath" in info:
        filepath = info["filepath"]

    elapsed = time.time() - start

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=500,
            detail="Download finished but file path not found."
        )

    print(f"[yt-dlp] Downloaded in {elapsed:.2f}s → {filepath}")
    return filepath, elapsed


# -----------------------------
# /api/download endpoint
# -----------------------------
@app.get("/api/download")
async def api_download(
    url: str = Query(..., description="YouTube Video URL"),
    type: str = Query("video", description="audio or video"),
    show_time: bool = Query(False, description="Show processing time page"),
):
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Base options for yt-dlp (with COOKIES)
    base_opts = {
        "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        "extractor_args": {"youtube": {"player_client": ["default"]}},
        "noplaylist": True,
        "quiet": True,
    }

    # AUDIO mode
    if type == "audio":
        ydl_opts = {
            **base_opts,
            "format": "bestaudio/best",
        }

    # VIDEO mode
    else:
        ydl_opts = {
            **base_opts,
            "format": "bestvideo[height<=720]+bestaudio/best/best[height<=720]",
        }

    filepath, elapsed = download_with_ytdlp(url, ydl_opts)
    filename = os.path.basename(filepath)

    # If show_time = true → HTML page + auto download
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


# -----------------------------
# File server route
# -----------------------------
@app.get("/file/{filename}")
async def get_file(filename: str):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename, media_type="application/octet-stream")


# -----------------------------
# Root info
# -----------------------------
@app.get("/")
async def root():
    return {
        "status": "OK",
        "message": "yt-dlp backend online",
        "example": "/api/download?url=https://youtu.be/VIDEO_ID&type=video&show_time=true",
    }


# -----------------------------
# Run locally
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
