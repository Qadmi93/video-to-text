import os
import flet as ft
import asyncio
import json
import datetime
import logging
from flet_permission_handler import PermissionHandler, Permission
from groq import Groq

# Configure logging to show up in logcat
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MobileGroqEngine:
    def __init__(self, api_key="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"):
        self.api_key = api_key

    def validate_file(self, file_path):
        """Checks if file exists and is within Groq's 25MB limit."""
        if not os.path.exists(file_path):
            raise FileNotFoundError("File not found.")
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 25:
            raise ValueError(f"File too large ({file_size_mb:.1f}MB). Groq limit is 25MB. Please use a shorter clip.")
        return True

    async def transcribe(self, file_path):
        if not self.api_key:
            raise ValueError("API Key is missing!")
        
        client = Groq(api_key=self.api_key)
        
        def call_groq():
            with open(file_path, "rb") as file:
                return client.audio.transcriptions.create(
                    file=(file_path, file.read()),
                    model="whisper-large-v3",
                    response_format="verbose_json"
                )
        
        response = await asyncio.to_thread(call_groq)
        
        segments = []
        raw_segments = getattr(response, "segments", [])
        for s in raw_segments:
            seg = {
                "text": s.get("text", "") if isinstance(s, dict) else getattr(s, "text", ""),
                "start": s.get("start", 0.0) if isinstance(s, dict) else getattr(s, "start", 0.0),
                "end": s.get("end", 0.0) if isinstance(s, dict) else getattr(s, "end", 0.0),
            }
            segments.append(seg)
            
        return {"text": response.text, "segments": segments}

    def format_timestamp(self, seconds: float):
        """Converts seconds to SRT timestamp format: HH:MM:SS,mmm"""
        tdelta = datetime.timedelta(seconds=seconds)
        str_td = str(tdelta)
        if "." in str_td:
            time_part, micro_part = str_td.split(".")
            milli_part = micro_part[:3].ljust(3, "0")
        else:
            time_part = str_td
            milli_part = "000"
            
        parts = time_part.split(":")
        if len(parts[0]) == 1:
            parts[0] = "0" + parts[0]
        time_part = ":".join(parts)
            
        return f"{time_part},{milli_part}"

    def generate_srt(self, segments):
        """Converts segments into a formatted SRT string."""
        srt_content = ""
        for i, segment in enumerate(segments, start=1):
            start = self.format_timestamp(segment['start'])
            end = self.format_timestamp(segment['end'])
            text = segment['text'].strip()
            srt_content += f"{i}\n{start} --> {end}\n{text}\n\n"
        return srt_content

    def save_srt_file(self, video_path, srt_content):
        """Saves SRT subtitle file to the public Downloads folder."""
        # Use just the filename (not full path) to avoid content URI issues on Android
        video_filename = os.path.basename(video_path)
        base_name, _ = os.path.splitext(video_filename)
        srt_filename = f"{base_name}.srt"
        
        # Try public Downloads folder first (visible in Files app)
        downloads_dir = "/storage/emulated/0/Download"
        if os.path.isdir(downloads_dir):
            srt_path = os.path.join(downloads_dir, srt_filename)
        else:
            # Fallback to app's own files directory
            srt_path = os.path.join(os.getcwd(), srt_filename)
        
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        logger.info(f"SRT file saved to: {srt_path}")
        return srt_path

async def main(page: ft.Page):
    try:
        logger.info("App starting...")
        page.title = "Groq Video-to-Text"
        page.theme_mode = ft.ThemeMode.DARK
        page.scroll = ft.ScrollMode.ADAPTIVE
        page.padding = 20
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        
        # Health check UI
        page.add(ft.Text("UI Engine: OK", color="green", size=10))

        # Request storage permissions at startup
        ph = PermissionHandler()
        page.overlay.append(ph)
        page.update()
        try:
            storage_perm = await ph.request_async(Permission.STORAGE)
            logger.info(f"Storage permission status: {storage_perm}")
        except Exception as pe:
            logger.warning(f"Permission request failed (may be normal on desktop): {pe}")
        file_picker = ft.FilePicker()
        page.services.append(file_picker)

        async def handle_select_file(e):
            status_text.value = "Opening picker..."
            page.update()
            try:
                # In Flet 0.84.0, pick_files is async and returns results directly
                files = await file_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["mp4", "mkv", "avi", "mov", "webm", "flv", "mp3", "wav", "m4a", "flac"]
                )
                
                if files and len(files) > 0:
                    nonlocal selected_video_path
                    selected_video_path = files[0].path
                    btn_select.text = f"Selected: {files[0].name}"
                    btn_select.color = "green"
                    btn_start.disabled = False
                    status_text.value = "Ready"
                else:
                    status_text.value = "Cancelled"
                page.update()
                
            except Exception as ex:
                status_text.value = f"Picker Error: {str(ex)}"
                page.update()

        # State management
        selected_video_path = None
        engine = MobileGroqEngine()
        
        status_text = ft.Text("Ready", color="grey400", size=16)
        progress_bar = ft.ProgressBar(width=350, color="cyan", visible=False)
        
        result_box = ft.TextField(
            label="Transcription Result", 
            multiline=True, 
            min_lines=8, 
            max_lines=12, 
            read_only=True,
            border_color="grey700",
            width=350
        )
        
        check_save_srt = ft.Checkbox(label="Save SRT Subtitle File", value=True)
        async def start_transcription(e):
            nonlocal selected_video_path
            # API Key is now hardcoded in MobileGroqEngine
            
            btn_start.disabled = True
            btn_select.disabled = True
            progress_bar.visible = True
            status_text.value = "Preparing file..."
            status_text.color = "cyan"
            page.update()

            try:
                # Validate file size (Groq has 25MB limit)
                await asyncio.to_thread(engine.validate_file, selected_video_path)
                
                status_text.value = "Uploading to Groq..."
                page.update()
                
                result = await engine.transcribe(selected_video_path)
                transcript = result["text"]
                segments = result["segments"]
                
                result_box.value = transcript
                status_text.value = "Transcription Finished!"
                status_text.color = "green"
                page.update()

                if check_save_srt.value and segments:
                    status_text.value = "Generating SRT file..."
                    status_text.color = "cyan"
                    page.update()
                    
                    try:
                        srt_content = engine.generate_srt(segments)
                        srt_path = await asyncio.to_thread(
                            engine.save_srt_file, selected_video_path, srt_content
                        )
                        status_text.value = f"Done! SRT saved:\n{os.path.basename(srt_path)}\n\nOpen with VLC or MX Player!"
                        status_text.color = "green"
                    except Exception as srt_ex:
                        status_text.value = f"SRT Save Error: {str(srt_ex)}"
                        status_text.color = "red"
                    
            except Exception as ex:
                status_text.value = f"Error: {str(ex)}"
                status_text.color = "red"
                if "25MB" in str(ex):
                    page.snack_bar = ft.SnackBar(ft.Text("File exceeds 25MB limit!"))
                    page.snack_bar.open = True
            
            btn_start.disabled = False
            btn_select.disabled = False
            progress_bar.visible = False
            page.update()

        btn_select = ft.ElevatedButton(
            "Select Video/Audio", 
            on_click=handle_select_file,
            width=350,
            height=50
        )
        
        btn_start = ft.ElevatedButton(
            "Start Transcription", 
            on_click=start_transcription,
            disabled=True,
            width=350,
            height=50,
            style=ft.ButtonStyle(bgcolor="cyan900", color="white")
        )

        page.add(
            ft.SafeArea(
                ft.Column(
                    [
                        ft.Text("Mobile Transcriber", size=28, weight="bold", color="cyan"),
                        ft.Text("Cloud-optimized for Android", size=14, italic=True),
                        ft.Text("Note: Max file size is 25MB", size=12, color="grey500"),
                        ft.Divider(height=10),
                        check_save_srt,
                        btn_select,
                        btn_start,
                        status_text,
                        progress_bar,
                        result_box,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=20,
                    scroll=ft.ScrollMode.ADAPTIVE
                )
            )
        )
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
        # If possible, show the error on the page
        try:
            page.add(ft.Text(f"CRITICAL ERROR: {str(e)}", color="red"))
        except:
            pass

if __name__ == "__main__":
    ft.app(target=main)
