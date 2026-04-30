import os
import flet as ft
import tempfile
import asyncio
import subprocess
import json
from groq import Groq

class MobileGroqEngine:
    def __init__(self, api_key=None):
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
    page.title = "Groq Video-to-Text"
    page.theme_mode = "dark"
    page.window_width = 400
    page.window_height = 800
    page.window_resizable = False
    page.scroll = "adaptive"
    page.padding = 30
    
    # Pre-initialize FilePicker
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    
    # Use client_storage for persistence on mobile
    def load_saved_key():
        return page.client_storage.get("groq_api_key") or ""

    def save_key(key):
        page.client_storage.set("groq_api_key", key)

    # State management
    selected_video_path = None
    engine = MobileGroqEngine()
    initial_key = load_saved_key()

    # UI Elements
    api_input = ft.TextField(
        label="Groq API Key", 
        password=True, 
        can_reveal_password=True,
        value=initial_key,
        border_color="cyan700",
        hint_text="Enter your API key..."
    )
    
    status_text = ft.Text("Ready", color="grey400", size=16)
    progress_bar = ft.ProgressBar(width=400, color="cyan", visible=False)
    
    result_box = ft.TextField(
        label="Transcription Result", 
        multiline=True, 
        min_lines=10, 
        max_lines=15, 
        read_only=True,
        border_color="grey700"
    )

    async def handle_select_file(e):
        nonlocal selected_video_path
        status_text.value = "Opening file picker..."
        page.update()
        
        result = await file_picker.pick_files(allow_multiple=False)
        
        if result and result.files:
            selected_video_path = result.files[0].path
            btn_select.text = f"Selected: {result.files[0].name}"
            btn_select.color = "green"
            btn_start.disabled = False
        
        status_text.value = "Ready"
        page.update()

    async def start_transcription(e):
        nonlocal selected_video_path
        if not api_input.value:
            page.snack_bar = ft.SnackBar(ft.Text("Please enter an API Key!"))
            page.snack_bar.open = True
            page.update()
            return

        save_key(api_input.value)
        engine.api_key = api_input.value
        
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
        "Select Video", 
        icon="video_library", 
        on_click=handle_select_file,
        width=400,
        height=50
    )
    
    btn_start = ft.ElevatedButton(
        "Start Transcription", 
        icon="bolt", 
        on_click=start_transcription,
        disabled=True,
        width=400,
        height=50,
        style=ft.ButtonStyle(bgcolor="cyan900", color="white")
    )

    page.add(
        ft.Column(
            [
                ft.Text("Mobile Transcriber", size=32, weight="bold", color="cyan"),
                ft.Text("Cloud-optimized for Android", size=14, italic=True),
                ft.Text("Note: Max file size is 25MB (Groq limit)", size=12, color="grey500"),
                ft.Divider(height=20),
                api_input,
                btn_select,
                btn_start,
                status_text,
                progress_bar,
                result_box,
            ],
            horizontal_alignment="center",
            spacing=25
        )
    )

if __name__ == "__main__":
    ft.app(target=main)
