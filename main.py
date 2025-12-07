import os
import uuid
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from yt_dlp import YoutubeDL

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Simple yt-dlp API (GET download)")


def download_with_ytdlp(url: str, ydl_opts: dict):
    """
    yt-dlp se file download karega aur:
    - final file ka path return karega
    - processing time return karega
    """
    start = time.time()

    # unique filename pattern
    unique_id = str(uuid.uuid4())[:8]
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_DIR, f"{unique_id}-%(title)s.%(ext)s")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        print("yt-dlp error:", repr(e))
        raise HTTPException(status_code=400, detail=f"yt-dlp error: {e}")

    # filepath nikalne ke liye safer way
    filepath = None

    # Newer yt-dlp: requested_downloads list me hota hai
    if isinstance(info, dict):
        if "requested_downloads" in info and info["requested_downloads"]:
            filepath = info["requested_downloads"][0].get("filepath")
        elif "filepath" in info:
            filepath = info["filepath"]

    elapsed = time.time() - start

    if not filepath or not os.path.exists(filepath):
        print("DEBUG: info from yt-dlp:", info)
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
    show_time: bool = Query(False, description="Show processing time in browser instead of direct download"),
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

    if type == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [],   # NO mp3 conversion
            "noplaylist": True,
            "quiet": True,
        }
    else:
        ydl_opts = {
            # 720p limit for speed
            "format": "bestvideo[height<=720]+bestaudio/best/best[height<=720]",
            "postprocessors": [],   # NO mp3 conversion
            "noplaylist": True,
            "quiet": True,
        }

    filepath, elapsed = download_with_ytdlp(url, ydl_opts)
    filename = os.path.basename(filepath)

    # 👉 Agar tum time browser me dekhna chahte ho + automatic download
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

            <!-- Auto-download via hidden iframe -->
            <iframe src="/file/{filename}" style="display:none;"></iframe>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    # normal: direct download (no HTML)
    return FileResponse(
        filepath,
        filename=filename,
        media_type="application/octet-stream",
        headers={"X-Processing-Time": f"{elapsed:.3f}s"},
    )


@app.get("/file/{filename}")
async def get_file(filename: str):
    """
    File serve karega (show_time page ke iframe se call hota hai).
    """
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename, media_type="application/octet-stream")


@app.get("/")
async def root():
    return {
        "message": "API running",
        "example_video": "/api/download?url=https://youtu.be/VIDEO_ID&type=video",
        "example_audio": "/api/download?url=https://youtu.be/VIDEO_ID&type=audio",
        "example_video_show_time": "/api/download?url=https://youtu.be/VIDEO_ID&type=video&show_time=true",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
