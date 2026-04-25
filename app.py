import os
import threading
import subprocess
import datetime
import math
import tempfile
import numpy as np
import whisper
import imageio_ffmpeg
import torch
import customtkinter as ctk
from tkinter import filedialog, messagebox

# --- Business Logic: Transcription Engine ---

class TranscriptionEngine:
    """Handles the heavy lifting of audio extraction and transcription."""
    
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def set_model_size(self, size):
        """Updates the model size and clears the cached model if it changed."""
        if size != self.model_size:
            self.model_size = size
            self._model = None # Clear cached model to force reload

    @property
    def model(self):
        """Lazy loading of the Whisper model."""
        if self._model is None:
            print(f"Loading Whisper model: {self.model_size}...")
            self._model = whisper.load_model(self.model_size, device=self.device)
        return self._model

    def extract_audio(self, video_path):
        """Extracts audio from video and returns it as a 16kHz mono numpy array."""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        cmd = [
            ffmpeg_exe,
            "-nostdin",
            "-threads", "0",
            "-i", video_path,
            "-f", "s16le",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-"
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        audio_chunks = []
        chunk_size = 4096
        
        while True:
            block = process.stdout.read(chunk_size)
            if not block:
                break
            audio_chunks.append(np.frombuffer(block, np.int16))
            
        _, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")

        return np.concatenate(audio_chunks).astype(np.float32) / 32768.0

    def format_timestamp(self, seconds: float):
        """Converts seconds to SRT timestamp format: HH:MM:SS,mmm"""
        tdelta = datetime.timedelta(seconds=seconds)
        str_td = str(tdelta)
        if "." in str_td:
            time_part, micro_part = str_td.split(".")
            milli_part = micro_part[:3]
        else:
            time_part = str_td
            milli_part = "000"
            
        # Ensure HH:MM:SS format
        parts = time_part.split(":")
        if len(parts[0]) == 1:
            parts[0] = "0" + parts[0]
        time_part = ":".join(parts)
            
        return f"{time_part},{milli_part}"

    def generate_srt(self, segments):
        """Converts Whisper segments into a formatted SRT string."""
        srt_content = ""
        for i, segment in enumerate(segments, start=1):
            start = self.format_timestamp(segment['start'])
            end = self.format_timestamp(segment['end'])
            text = segment['text'].strip()
            srt_content += f"{i}\n{start} --> {end}\n{text}\n\n"
        return srt_content

    def transcribe(self, audio_array, callback=None):
        """Runs the transcription using the Whisper model."""
        result = self.model.transcribe(
            audio_array, 
            fp16=torch.cuda.is_available(),
            verbose=False
        )
        
        # If a callback is provided, we simulate the live feed by iterating
        if callback and "segments" in result:
            for segment in result["segments"]:
                callback(segment)

        return result

    def burn_subtitles(self, video_path, srt_path, output_path):
        """Hardcodes subtitles into a video file using FFmpeg filters."""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        # FFmpeg subtitle filter needs specific escaping for Windows paths
        # Convert C:\path\file.srt to C\\:/path/file.srt
        escaped_path = srt_path.replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            ffmpeg_exe,
            "-y", # Overwrite output if it exists
            "-i", video_path,
            "-vf", f"subtitles='{escaped_path}'",
            "-c:a", "copy", # Copy audio stream without re-encoding to save time
            output_path
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg burning error: {stderr.decode('utf-8', errors='ignore')}")

# --- UI Logic: Modern Application ---

class VideoToTextApp(ctk.CTk):
    """Modern UI for the Video to Text Transcriber."""
    
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Video to Text Transcriber")
        self.geometry("600x600")
        ctk.set_appearance_mode("dark")  # Options: "System", "Light", "Dark"
        ctk.set_default_color_theme("blue")  # Options: "blue", "green", "dark-blue"

        # Engine Initialization
        self.engine = TranscriptionEngine()

        # UI Elements
        self.setup_ui()

    def setup_ui(self):
        """Initializes the layout and widgets."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) # Allow the textbox to expand

        # Title/Instruction
        self.lbl_title = ctk.CTkLabel(self, text="Video to Text", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Model Selection Frame
        self.frame_settings = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_settings.grid(row=1, column=0, padx=20, pady=0)
        
        self.lbl_model = ctk.CTkLabel(self.frame_settings, text="Model Size:", font=ctk.CTkFont(size=13))
        self.lbl_model.pack(side="left", padx=10)
        
        self.combo_model = ctk.CTkComboBox(self.frame_settings, 
                                          values=["tiny", "base", "small", "medium", "large", "turbo"], 
                                          command=self.handle_model_change)
        self.combo_model.set("base")
        self.combo_model.pack(side="left", padx=10)

        # Main Action Button
        self.btn_select = ctk.CTkButton(self, text="Start Transcribe", 
                                        command=self.handle_select_file,
                                        height=45, corner_radius=10,
                                        font=ctk.CTkFont(size=15, weight="bold"))
        self.btn_select.grid(row=2, column=0, padx=20, pady=10)

        # Burn Subtitles Checkbox
        self.check_burn = ctk.CTkCheckBox(self, text="Burn subtitles into video?")
        self.check_burn.grid(row=4, column=0, padx=20, pady=5)

        # Live Transcript Textbox
        self.textbox = ctk.CTkTextbox(self, height=200, corner_radius=10)
        self.textbox.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        self.textbox.insert("0.0", "Transcription will appear here...")

        # Status & Progress
        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="#2ecc71") # Greenish
        self.lbl_status.grid(row=5, column=0, padx=20, pady=5)

        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", mode="indeterminate")
        self.progress_bar.set(0) # Initially empty

    def handle_model_change(self, value):
        """Updates the engine model size when the dropdown changes."""
        self.engine.set_model_size(value)
        self.update_status(f"Model set to {value}", "cyan")

    def update_status(self, text, color=None):
        """Thread-safe status update."""
        def task():
            self.lbl_status.configure(text=f"Status: {text}")
            if color:
                self.lbl_status.configure(text_color=color)
        self.after(0, task)

    def engine_callback(self, segment):
        """Called by the engine for each new segment transcribed."""
        text = segment['text'].strip()
        def task():
            self.textbox.insert("end", f"\n{text}")
            self.textbox.see("end")
        self.after(0, task)

    def handle_select_file(self):
        """Opens file dialog and starts processing."""
        file_path = filedialog.askopenfilename(
            title="Select Video",
            filetypes=(("MP4 files", "*.mp4"), ("All files", "*.*"))
        )
        
        if file_path:
            self.start_processing(file_path)

    def start_processing(self, file_path):
        """Prepares the UI and starts the background thread."""
        self.btn_select.configure(state="disabled")
        self.combo_model.configure(state="disabled")
        self.check_burn.configure(state="disabled")
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", "Starting transcription...")
        self.progress_bar.grid(row=6, column=0, padx=20, pady=10)
        self.progress_bar.start()
        self.update_status("Processing... Please wait.", "yellow")

        # Background Execution
        should_burn = self.check_burn.get()
        thread = threading.Thread(target=self.process_video_task, args=(file_path, should_burn), daemon=True)
        thread.start()

    def process_video_task(self, video_path, should_burn):
        """The worker method running in a separate thread."""
        try:
            self.update_status("Extracting audio...", "cyan")
            audio_data = self.engine.extract_audio(video_path)
            
            self.update_status("Transcribing (Whisper)...", "orange")
            result = self.engine.transcribe(audio_data, callback=self.engine_callback)
            
            # Switch back to main thread for UI/Dialogs
            self.after(0, lambda: self.finish_processing(video_path, result, should_burn))
            
        except Exception as e:
            self.after(0, lambda: self.handle_error(str(e)))

    def finish_processing(self, video_path, result, should_burn):
        """Cleans up UI and prompts to save."""
        self.progress_bar.stop()
        self.progress_bar.grid_forget()
        self.btn_select.configure(state="normal")
        self.combo_model.configure(state="normal")
        self.check_burn.configure(state="normal")
        self.update_status("Finished!", "#2ecc71")

        transcript_text = result["text"].strip()
        segments = result.get("segments", [])

        # 1. Save Text/SRT Result
        suggested_name = os.path.splitext(os.path.basename(video_path))[0]
        save_path = filedialog.asksaveasfilename(
            title="Save Transcription/Subtitles",
            initialfile=suggested_name,
            filetypes=(("Text files", "*.txt"), ("Subtitles", "*.srt"), ("All files", "*.*"))
        )
        
        if save_path:
            if save_path.endswith(".srt"):
                content = self.engine.generate_srt(segments)
            else:
                content = transcript_text
                
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # 2. Handle Video Burning if requested
            if should_burn:
                self.handle_video_burn(video_path, segments, suggested_name)
            else:
                messagebox.showinfo("Success", f"File saved successfully to:\n{save_path}")
        else:
            messagebox.showwarning("Cancelled", "Transcription was not saved.")

    def handle_video_burn(self, video_path, segments, suggested_name):
        """Helper to manage the video encoding process."""
        output_video = filedialog.asksaveasfilename(
            title="Save Subtitled Video",
            initialfile=f"{suggested_name}_subtitled.mp4",
            filetypes=(("MP4 Video", "*.mp4"), ("All files", "*.*"))
        )

        if output_video:
            # We need the SRT content in a file for FFmpeg to read
            srt_content = self.engine.generate_srt(segments)
            
            # Use a background thread for the heavy encoding task
            self.update_status("Burning subtitles... (May take a while)", "orange")
            self.btn_select.configure(state="disabled")
            
            def burn_task():
                try:
                    # Create a temporary SRT file
                    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8") as tf:
                        tf.write(srt_content)
                        temp_srt_path = tf.name
                    
                    try:
                        self.engine.burn_subtitles(video_path, temp_srt_path, output_video)
                        self.after(0, lambda: messagebox.showinfo("Success", f"Video saved successfully to:\n{output_video}"))
                        self.update_status("Video Complete!", "#2ecc71")
                    finally:
                        # Clean up the temp file
                        if os.path.exists(temp_srt_path):
                            os.remove(temp_srt_path)
                except Exception as e:
                    self.after(0, lambda: self.handle_error(str(e)))
                finally:
                    self.after(0, lambda: self.btn_select.configure(state="normal"))

            threading.Thread(target=burn_task, daemon=True).start()
        else:
            messagebox.showinfo("Finished", "Transcription saved, but video export was cancelled.")

    def handle_error(self, error_msg):
        """Handles errors by updating status and showing a dialog."""
        self.progress_bar.stop()
        self.progress_bar.grid_forget()
        self.btn_select.configure(state="normal")
        self.combo_model.configure(state="normal")
        self.update_status("Error encountered.", "#e74c3c") # Red
        messagebox.showerror("Error", f"An error occurred:\n{error_msg}")

if __name__ == "__main__":
    # Ensure high-DPI awareness on Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = VideoToTextApp()
    app.mainloop()
