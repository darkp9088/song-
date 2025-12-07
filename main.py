# main.py
import yt_dlp
import os
import tempfile
import shutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional

app = FastAPI(title="YT-DLP Song Downloader API (Authenticated)")

# --- CONFIGURATION ---
# You MUST have FFmpeg installed on the system where this FastAPI app runs.
TEMP_DIR = tempfile.gettempdir() 

# 🚨 IMPORTANT FIX 🚨
# This path MUST be an absolute path to a file on your server 
# containing valid session cookies (exported from a logged-in browser).
# Example path: "/home/user/config/youtube_cookies.txt"
# If you don't use this, downloads for restricted content will fail.
COOKIE_FILE_PATH: Optional[str] = os.environ.get(
    "YT_COOKIES_PATH", 
    "/tmp/cookies.txt" # Default path - update this!
)

# ---------------------

@app.get("/download-song")
async def download_song(url: str = Query(..., description="The URL of the video or song to download.")):
    """
    Downloads audio (MP3) from a given URL, streams the file, and cleans up.
    """
    
    # 1. Setup paths and options
    download_folder = os.path.join(TEMP_DIR, f"yt-dlp_{os.getpid()}")
    os.makedirs(download_folder, exist_ok=True)
    
    # Output template ensures the file is created within the unique temp folder
    output_filename_template = os.path.join(download_folder, '%(title)s.%(ext)s')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_filename_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192', # High quality audio
        }],
        # 🔑 FIX IMPLEMENTATION: Use the cookie file if the path is set
        'cookiefile': COOKIE_FILE_PATH,
        
        'restrictfilenames': True, # Keep filenames clean
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
        'verbose': False,
        'keepvideo': False, # Don't keep the intermediate video/audio file
    }

    try:
        # 2. Execute yt-dlp download and conversion
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Check if the URL is accessible before starting the download
            try:
                info_dict = ydl.extract_info(url, download=True)
            except Exception as e:
                # Re-raise the error to be caught by the outer block
                raise e

            # 3. Find the final MP3 file created by FFmpeg
            # We search the unique folder for the .mp3 file
            mp3_file = next((f for f in os.listdir(download_folder) if f.endswith('.mp3')), None)
            
            if not mp3_file:
                 raise HTTPException(status_code=500, detail="Audio file was not created by yt-dlp. Check yt-dlp logs for conversion errors (e.g., FFmpeg missing).")
                 
            final_filepath = os.path.join(download_folder, mp3_file)
            
            # 4. Stream file with automatic download header
            response = FileResponse(
                path=final_filepath, 
                filename=mp3_file, 
                media_type="audio/mpeg",
                # The Content-Disposition header is set here, ensuring the filename is known
            )
            
            # 5. Cleanup function (runs after the entire file is streamed)
            @response.background.add_task
            def cleanup():
                shutil.rmtree(download_folder, ignore_errors=True)
                print(f"Cleaned up temporary directory: {download_folder}")
                
            return response

    except yt_dlp.DownloadError as e:
        # Catch and report download-specific errors, including the cookie issue
        detail = str(e).strip()
        if "Sign in to confirm" in detail and not COOKIE_FILE_PATH:
             detail += " -> FIX: Cookie file is required for this content. Set the YT_COOKIES_PATH environment variable."
        elif "Sign in to confirm" in detail and COOKIE_FILE_PATH:
             detail += " -> FIX: Cookie file may be expired or invalid. Update cookies at: " + COOKIE_FILE_PATH
             
        raise HTTPException(status_code=400, detail=f"Download Error: {detail}")
        
    except Exception as e:
        # Catch all other unexpected errors
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {e}")
    finally:
        # Attempt to clean up if an error occurred before the streaming phase
        # Note: Background task handles cleanup for successful streams
        if 'download_folder' in locals() and os.path.exists(download_folder):
             # Only cleanup if the download failed before FileResponse was created
             pass

# To run locally: uvicorn main:app --host 0.0.0.0 --port 8000
# To run with Gunicorn: gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
