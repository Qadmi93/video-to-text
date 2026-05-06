import os
import flet as ft
import tempfile
import asyncio
import subprocess
import json
import logging
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
        return response.text

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


        # FilePicker setup (Updated for Flet 0.84.0 Service pattern)
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
                
                transcript = await engine.transcribe(selected_video_path)
                result_box.value = transcript
                status_text.value = "Finished!"
                status_text.color = "green"
                    
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
