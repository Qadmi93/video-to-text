import os
import threading
import subprocess
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

    def transcribe(self, audio_array):
        """Runs the transcription using the Whisper model."""
        result = self.model.transcribe(audio_array, fp16=torch.cuda.is_available())
        return result["text"].strip()

# --- UI Logic: Modern Application ---

class VideoToTextApp(ctk.CTk):
    """Modern UI for the Video to Text Transcriber."""
    
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Video to Text Transcriber")
        self.geometry("500x350")
        ctk.set_appearance_mode("dark")  # Options: "System", "Light", "Dark"
        ctk.set_default_color_theme("blue")  # Options: "blue", "green", "dark-blue"

        # Engine Initialization
        self.engine = TranscriptionEngine()

        # UI Elements
        self.setup_ui()

    def setup_ui(self):
        """Initializes the layout and widgets."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # Title/Instruction
        self.lbl_title = ctk.CTkLabel(self, text="Video to Text", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Model Selection Frame
        self.frame_settings = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_settings.grid(row=1, column=0, padx=20, pady=0)
        
        self.lbl_model = ctk.CTkLabel(self.frame_settings, text="Model Size:", font=ctk.CTkFont(size=13))
        self.lbl_model.pack(side="left", padx=10)
        
        self.combo_model = ctk.CTkComboBox(self.frame_settings, values=["tiny", "base", "small"], 
                                          command=self.handle_model_change)
        self.combo_model.set("base")
        self.combo_model.pack(side="left", padx=10)

        self.lbl_info = ctk.CTkLabel(self, text="Select an MP4 video to generate a text transcript.", text_color="gray")
        self.lbl_info.grid(row=2, column=0, padx=20, pady=(10, 0))

        # Main Action Button
        self.btn_select = ctk.CTkButton(self, text="Start Transcribe", 
                                        command=self.handle_select_file,
                                        height=45, corner_radius=10,
                                        font=ctk.CTkFont(size=15, weight="bold"))
        self.btn_select.grid(row=3, column=0, padx=20, pady=20)

        # Status & Progress
        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="#2ecc71") # Greenish
        self.lbl_status.grid(row=4, column=0, padx=20, pady=5)

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
        self.progress_bar.grid(row=5, column=0, padx=20, pady=10)
        self.progress_bar.start()
        self.update_status("Processing... Please wait.", "yellow")

        # Background Execution
        thread = threading.Thread(target=self.process_video_task, args=(file_path,), daemon=True)
        thread.start()

    def process_video_task(self, video_path):
        """The worker method running in a separate thread."""
        try:
            self.update_status("Extracting audio...", "cyan")
            audio_data = self.engine.extract_audio(video_path)
            
            self.update_status("Transcribing (Whisper)...", "orange")
            transcript = self.engine.transcribe(audio_data)
            
            # Switch back to main thread for UI/Dialogs
            self.after(0, lambda: self.finish_processing(video_path, transcript))
            
        except Exception as e:
            self.after(0, lambda: self.handle_error(str(e)))

    def finish_processing(self, video_path, transcript):
        """Cleans up UI and prompts to save."""
        self.progress_bar.stop()
        self.progress_bar.grid_forget()
        self.btn_select.configure(state="normal")
        self.combo_model.configure(state="normal")
        self.update_status("Finished!", "#2ecc71")

        # Save Logic
        suggested_name = os.path.splitext(os.path.basename(video_path))[0] + ".txt"
        save_path = filedialog.asksaveasfilename(
            title="Save Transcript",
            initialfile=suggested_name,
            defaultextension=".txt",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )
        
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            messagebox.showinfo("Success", "Transcript saved successfully!")
        else:
            messagebox.showwarning("Cancelled", "Transcript was not saved.")

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
