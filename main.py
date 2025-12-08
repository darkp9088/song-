import os
import uuid
import time
from urllib.error import HTTPError

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pytube import YouTube

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Pytube Example API (Debug)")


def download_with_pytube(url: str, media_type: str):
    start = time.time()

    # --- YouTube object banaye ---
    try:
        yt = YouTube(url)
    except HTTPError as e:
        # YouTube ne direct HTTP error de diya
        raise HTTPException(
            status_code=400,
            detail=f"YouTube HTTP error (init): {e.__class__.__name__}: {e}"
        )
    except Exception as e:
        # yahan hame exact class + message chahiye
        raise HTTPException(
            status_code=400,
            detail=f"YouTube init error: {e.__class__.__name__}: {e}"
        )

    unique_id = str(uuid.uuid4())[:8]

    # --- AUDIO MODE ---
    if media_type == "audio":
        stream = (
            yt.streams
            .filter(only_audio=True)
            .order_by("abr")
            .desc()
            .first()
        )
    else:
        # --- VIDEO MODE (pytube official example style) ---
        stream = (
            yt.streams
            .filter(progressive=True, file_extension="mp4")
            .order_by("resolution")
            .desc()
            .first()
        )

    if not stream:
        raise HTTPException(
            status_code=404,
            detail="No valid stream found for this URL (pytube returned no stream)."
        )

    original_filename = stream.default_filename  # e.g. "Video Title.mp4"
    final_filename = f"{unique_id}-{original_filename}"
    final_path = os.path.join(DOWNLOAD_DIR, final_filename)

    try:
        stream.download(output_path=DOWNLOAD_DIR, filename=final_filename)
    except HTTPError as e:
        raise HTTPException(
            status_code=400,
            detail=f"YouTube HTTP error (download): {e.__class__.__name__}: {e}"
        )
    except Exception as e:
        # yaha bhi exact error class + message dikhaenge
        raise HTTPException(
            status_code=500,
            detail=f"Download error: {e.__class__.__name__}: {e}"
        )

    elapsed = time.time() - start

    if not os.path.exists(final_path):
        raise HTTPException(
            status_code=500,
            detail="Download finished but file not found on disk."
        )

    print(f"[pytube] Downloaded in {elapsed:.2f} seconds -> {final_path}")
    return final_path, elapsed


@app.get("/api/download")
async def api_download(
    url: str = Query(..., description="YouTube URL"),
    type: str = Query("video", description="audio or video"),
    show_time: bool = Query(
        False,
        description="true = show HTML with processing time; false = direct download",
    ),
):
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    media_type = "audio" if type.lower() == "audio" else "video"

    # Yahan koi generic `except Exception` nahi rakhenge,
    # taaki HTTPException ka detail seedha response me dikhe
    filepath, elapsed = download_with_pytube(url, media_type)
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
            <h2>Download complete ✅ (pytube)</h2>
            <p><b>Processing time:</b> {elapsed:.2f} seconds</p>
            <p><b>File:</b> {filename}</p>
            <p>If download didn't start automatically,
               <a href="/file/{filename}" download>click here</a>.
            </p>
            <iframe src="/file/{filename}" style="display:none;"></iframe>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

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
    return FileResponse(
        filepath,
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/")
async def root():
    return {
        "message": "Pytube API running ✅ (Debug)",
        "example_video": "/api/download?url=https://youtu.be/2lAe1cqCOXo&type=video",
        "example_audio": "/api/download?url=https://youtu.be/2lAe1cqCOXo&type=audio",
        "example_video_show_time": "/api/download?url=https://youtu.be/2lAe1cqCOXo&type=video&show_time=true",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
