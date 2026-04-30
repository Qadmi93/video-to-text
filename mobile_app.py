import os
import flet as ft
import tempfile
import asyncio
import subprocess
import json
import imageio_ffmpeg
from groq import Groq

class MobileGroqEngine:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def extract_audio(self, video_path):
        """Extracts audio to a temp wav file for Groq."""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        
        cmd = [
            ffmpeg_exe, "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            temp_wav
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return temp_wav

    async def transcribe(self, audio_path):
        if not self.api_key:
            raise ValueError("API Key is missing!")
        
        client = Groq(api_key=self.api_key)
        
        def call_groq():
            with open(audio_path, "rb") as file:
                return client.audio.transcriptions.create(
                    file=(audio_path, file.read()),
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
    page.window_resizable = False # Keep it phone-shaped
    page.scroll = "adaptive"
    page.padding = 30
    
    # Pre-initialize FilePicker and add it once (Fixes TimeoutException)
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    
    # Config File Logic (Shared with Desktop App)
    config_file = "config.json"
    
    def load_saved_key():
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)
                    return data.get("api_keys", {}).get("Groq (Cloud/Fast)", "")
            except:
                pass
        return ""

    def save_key(key):
        data = {"api_keys": {}}
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)
            except:
                pass
        
        if "api_keys" not in data:
            data["api_keys"] = {}
        
        data["api_keys"]["Groq (Cloud/Fast)"] = key
        
        try:
            with open(config_file, "w") as f:
                json.dump(data, f, indent=4)
        except:
            pass

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
        
        # Await the pre-initialized picker
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
        status_text.value = "Extracting audio..."
        status_text.color = "cyan"
        page.update()

        try:
            audio_path = await asyncio.to_thread(engine.extract_audio, selected_video_path)
            status_text.value = "Transcribing with Groq..."
            page.update()
            transcript = await engine.transcribe(audio_path)
            result_box.value = transcript
            status_text.value = "Finished!"
            status_text.color = "green"
            if os.path.exists(audio_path):
                os.remove(audio_path)
                
        except Exception as ex:
            status_text.value = f"Error: {str(ex)}"
            status_text.color = "red"
        
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
