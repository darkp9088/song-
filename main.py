import os
import uuid
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from pytube import YouTube
from pytube.exceptions import PytubeError

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = FastAPI(title="Simple pytube API (GET download)")


def download_with_pytube(url: str, media_type: str):
    """
    pytube se file download karega aur:
    - final file ka path return karega
    - processing time return karega
    """
    start = time.time()

    try:
        yt = YouTube(url)
    except Exception as e:
        print("pytube init error:", repr(e))
        raise HTTPException(status_code=400, detail=f"pytube error (init): {e}")

    # unique filename ID
    unique_id = str(uuid.uuid4())[:8]

    # 🔊 AUDIO DOWNLOAD
    if media_type == "audio":
        # best audio stream (usually webm/mp4)
        stream = (
            yt.streams.filter(only_audio=True)
            .order_by("abr")
            .desc()
            .first()
        )
        if not stream:
            raise HTTPException(status_code=404, detail="No audio stream found")
    else:
        # 🎥 VIDEO DOWNLOAD (progressive = audio + video together)
        # Pehle saare progressive mp4 streams lete hain
        progressive_streams = yt.streams.filter(progressive=True, file_extension="mp4")

        if not progressive_streams:
            raise HTTPException(
                status_code=404,
                detail="No progressive video stream (mp4) found",
            )

        # 720p limit try karenge: sab resolutions dekh ke <=720p ka highest choose
        best_stream = None
        best_res = 0
        for s in progressive_streams:
            if not s.resolution:
                continue
            try:
                res_int = int(s.resolution.replace("p", ""))
            except ValueError:
                continue

            # 720p se zyada nahi
            if res_int <= 720 and res_int > best_res:
                best_res = res_int
                best_stream = s

        # agar <=720p kuch na mile, toh sabse highest progressive le lo
        stream = best_stream or progressive_streams.order_by("resolution").desc().first()

        if not stream:
            raise HTTPException(
                status_code=404,
                detail="No suitable video stream found",
            )

    # Custom filename banayenge: <uuid>-<original_name>.<ext>
    # pytube ka default filename leke usme uuid prefix kar dete hain
    original_name = stream.default_filename  # e.g. "Video Title.mp4"
    final_filename = f"{unique_id}-{original_name}"
    output_path = DOWNLOAD_DIR

    try:
        filepath = stream.download(output_path=output_path, filename=final_filename)
    except Exception as e:
        print("pytube download error:", repr(e))
        raise HTTPException(status_code=500, detail=f"pytube error (download): {e}")

    elapsed = time.time() - start

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=500,
            detail="Download finished but file not found on disk.",
        )

    print(f"[pytube] Downloaded in {elapsed:.2f} seconds -> {filepath}")
    return filepath, elapsed


@app.get("/api/download")
async def api_download(
    url: str = Query(..., description="Video URL"),
    type: str = Query("video", description="audio or video"),
    show_time: bool = Query(
        False, description="Show processing time in browser instead of direct download"
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

    # yt-dlp waale options ki zaroorat nahi, pytube khud handle karega
    media_type = "audio" if type.lower() == "audio" else "video"

    try:
        filepath, elapsed = download_with_pytube(url, media_type)
    except HTTPException:
        # already proper error response
        raise
    except Exception as e:
        # generic fallback
        print("Unexpected error:", repr(e))
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

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
            <h2>Download complete ✅ (pytube)</h2>
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
        "message": "API running (pytube)",
        "example_video": "/api/download?url=https://youtu.be/VIDEO_ID&type=video",
        "example_audio": "/api/download?url=https://youtu.be/VIDEO_ID&type=audio",
        "example_video_show_time": "/api/download?url=https://youtu.be/VIDEO_ID&type=video&show_time=true",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
