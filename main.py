# main.py
import yt_dlp
import os
import tempfile
import shutil
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

app = FastAPI(title="YT-DLP Song Downloader API")

# --- Configuration ---
# You must have FFmpeg installed on the system where this FastAPI app runs.
TEMP_DIR = tempfile.gettempdir() # Use the system's temp directory

@app.get("/download-song")
async def download_song(url: str = Query(..., description="The URL of the video or song to download.")):
    """
    Downloads audio (MP3) from a given URL and returns it as a streaming file response.
    """
    
    # 1. Define temporary file path and options
    # Output template ensures the file is created with the title and .mp3 extension
    output_filename_template = os.path.join(TEMP_DIR, 'download_cache', '%(title)s.%(ext)s')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_filename_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192', # High quality audio
        }],
        'restrictfilenames': True, # Keep filenames clean
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
        'verbose': False,
        'keepvideo': False, # Don't keep the intermediate video/audio file
    }

    try:
        # Create a unique temporary directory for the download to avoid conflicts
        download_folder = os.path.join(TEMP_DIR, f"yt-dlp_{os.getpid()}")
        os.makedirs(download_folder, exist_ok=True)
        
        # Override output template to use the new unique folder
        ydl_opts['outtmpl'] = os.path.join(download_folder, '%(title)s.%(ext)s')

        # 2. Execute yt-dlp download and conversion
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            
            # yt-dlp gives the *final* output filename after post-processing
            final_filename = ydl.prepare_filename(info_dict)
            
            # The actual mp3 file will be named according to the template but with the final extension (.mp3)
            # Find the actual .mp3 file in the download directory
            mp3_file = next((f for f in os.listdir(download_folder) if f.endswith('.mp3')), None)
            
            if not mp3_file:
                 raise HTTPException(status_code=500, detail="Audio file was not created by yt-dlp.")
                 
            final_filepath = os.path.join(download_folder, mp3_file)
            
            # 3. Automatic Download Feature: Stream file with correct headers
            # FileResponse automatically sets Content-Type (audio/mpeg) and streams the file.
            # The 'filename' argument is crucial for the automatic download name.
            response = FileResponse(
                path=final_filepath, 
                filename=mp3_file, 
                media_type="audio/mpeg",
                # The Cloudflare Worker will add the 'Content-Disposition' header later.
                # For direct use, you can add it here:
                # headers={"Content-Disposition": f"attachment; filename=\"{mp3_file}\""}
            )
            
            # 4. Cleanup function (runs after the file is streamed)
            @response.background.add_task
            def cleanup():
                shutil.rmtree(download_folder, ignore_errors=True)
                print(f"Cleaned up temporary directory: {download_folder}")
                
            return response

    except yt_dlp.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Download Error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        # Emergency cleanup if something failed before the streaming started
        pass

# To run locally: uvicorn main:app --host 0.0.0.0 --port 8000
