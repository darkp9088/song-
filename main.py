import os
import uuid
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Audio Download API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Processing-Time", "Content-Disposition"]
)

def download_audio(url: str, output_id: str):
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{output_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Expected MP3 file
    final_path = os.path.join(DOWNLOAD_DIR, f"{output_id}.mp3")
    return final_path, info


@app.get("/api/audio")
async def get_audio(
    url: str = Query(...),
    filename: Optional[str] = Query(None)
):
    # Start timer
    start_time = time.time()

    # Unique output file id
    uid = uuid.uuid4().hex

    try:
        audio_path, info = download_audio(url, uid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    processing_time = round(time.time() - start_time, 3)

    print(f"[INFO] Processed audio in {processing_time} sec")

    # If user did not give filename, use video title
    if filename:
        safe_name = filename
    else:
        title = info.get("title", "audio")
        safe_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-"))

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}.mp3"',
        "X-Processing-Time": str(processing_time)
    }

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename=f"{safe_name}.mp3",
        headers=headers
    )
