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
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Simple yt-dlp API (Render compatible)")


def build_ydl_opts(media_type: str) -> dict:
    """
    yt-dlp options factory.
    No cookies, JS warning handled via extractor_args.
    """
    base_opts = {
        "noplaylist": True,
        "quiet": True,
        # Fix JavaScript runtime warning by forcing default client
        "extractor_args": {"youtube": {"player_client": ["default"]}},
    }

    if media_type == "audio":
        base_opts["format"] = "bestaudio/best"
    else:
        # video (720p max) + best audio
        base_opts["format"] = "bestvideo[height<=720]+bestaudio/best/best[height<=720]"

    return base_opts


def download_with_ytdlp(url: str, media_type: str):
    """
    Run yt-dlp download and return (filepath, elapsed_seconds).
    """
    start = time.time()

    ydl_opts = build_ydl_opts(media_type)

    # unique filename
    unique_id = str(uuid.uuid4())[:8]
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_DIR, f"{unique_id}-%(title)s.%(ext)s")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        # If YouTube blocks server IP with "Sign in to confirm" etc.
        msg = str(e)
        if "Sign in to confirm" in msg:
            raise HTTPException(
                status_code=403,
                detail=(
                    "YouTube is asking for sign-in / CAPTCHA for this video from server IP. "
                    "Try another video URL."
                ),
            )
        print("yt-dlp error:", repr(e))
        raise HTTPException(status_code=400, detail=f"yt-dlp error: {e}")

    # Resolve final filepath
    filepath = None
    if isinstance(info, dict):
        if "requested_downloads" in info and info["requested_downloads"]:
            filepath = info["requested_downloads"][0].get("filepath")
        elif "filepath" in info:
            filepath = info["filepath"]

    elapsed = time.time() - start

    if not filepath or not os.path.exists(filepath):
        print("DEBUG: yt-dlp info:", info)
        raise HTTPException(
            status_code=500,
            detail="Download finished but file path not found on disk.",
        )

    print(f"[yt-dlp] Downloaded in {elapsed:.2f} seconds -> {filepath}")
    return filepath, elapsed


@app.get("/api/download")
async def api_download(
    url: str = Query(..., description="Video URL"),
    type: str = Query("video", description="audio or video"),
    show_time: bool = Query(
        False,
        description="If true, show HTML page with processing time instead of direct download",
    ),
):
    """
    Example:
    - /api/download?url=...&type=audio
    - /api/download?url=...&type=video
    - /api/download?url=...&type=video&show_time=true
    """
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    media_type = "audio" if type.lower() == "audio" else "video"

    filepath, elapsed = download_with_ytdlp(url, media_type)
    filename = os.path.basename(filepath)

    if show_time:
        html = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Processing Time</title>
        </head>
        <body style="font-family:sans-serif;">
            <h2>Download complete ✅</h2>
            <p><b>Processing time:</b> {elapsed:.2f} seconds</p>
            <p><b>File:</b> {filename}</p>
            <p>If download didn't start automatically, <a href="/file/{filename}" download>click here</a>.</p>
            <iframe src="/file/{filename}" style="display:none;"></iframe>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    # Normal direct download
    return FileResponse(
        filepath,
        filename=filename,
        media_type="application/octet-stream",
        headers={"X-Processing-Time": f"{elapsed:.3f}s"},
    )


@app.get("/file/{filename}")
async def get_file(filename: str):
    """
    Serve a downloaded file.
    """
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename, media_type="application/octet-stream")


@app.get("/")
async def root():
    return {
        "status": "OK",
        "message": "yt-dlp FastAPI backend running",
        "example_video": "/api/download?url=https://youtu.be/VIDEO_ID&type=video",
        "example_audio": "/api/download?url=https://youtu.be/VIDEO_ID&type=audio",
        "example_video_show_time": "/api/download?url=https://youtu.be/VIDEO_ID&type=video&show_time=true",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
