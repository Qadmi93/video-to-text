import os
import threading
import subprocess
import datetime
import math
import tempfile
import numpy as np
from faster_whisper import WhisperModel
import whisper
import vosk
import json
import imageio_ffmpeg
import torch
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Optional imports for new engines
try:
    import stable_whisper
except ImportError:
    stable_whisper = None

try:
    import assemblyai as aai
except ImportError:
    aai = None

try:
    from groq import Groq
except ImportError:
    Groq = None

# --- Business Logic: Transcription Engines ---

class BaseEngine:
    """Common functionality for all transcription engines."""
    
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

        return np.concatenate(audio_chunks)

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

    def burn_subtitles(self, video_path, srt_path, output_path):
        """Hardcodes subtitles into a video file using FFmpeg filters."""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        escaped_path = srt_path.replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            ffmpeg_exe, "-y", "-i", video_path,
            "-vf", f"subtitles='{escaped_path}'",
            "-c:a", "copy", output_path
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg burning error: {stderr.decode('utf-8', errors='ignore')}")

class FasterWhisperEngine(BaseEngine):
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def set_model_size(self, size):
        if size != self.model_size:
            self.model_size = size
            self._model = None

    @property
    def model(self):
        if self._model is None:
            print(f"Loading Faster-Whisper model: {self.model_size}...")
            compute_type = "int8" if self.device == "cpu" else "float16"
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=compute_type)
        return self._model

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        audio_float = audio_data.astype(np.float32) / 32768.0
        segments, info = self.model.transcribe(audio_float, beam_size=5, task=task)
        
        all_segments = []
        full_text = ""
        for segment in segments:
            seg_dict = {'text': segment.text, 'start': segment.start, 'end': segment.end}
            all_segments.append(seg_dict)
            full_text += segment.text + " "
            if callback: callback(seg_dict)
        return {
            "text": full_text.strip(), 
            "segments": all_segments,
            "language": info.language,
            "language_probability": info.language_probability
        }

class StandardWhisperEngine(BaseEngine):
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def set_model_size(self, size):
        if size != self.model_size:
            self.model_size = size
            self._model = None

    @property
    def model(self):
        if self._model is None:
            print(f"Loading Standard Whisper model: {self.model_size}...")
            self._model = whisper.load_model(self.model_size, device=self.device)
        return self._model

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        audio_float = audio_data.astype(np.float32) / 32768.0
        result = self.model.transcribe(audio_float, fp16=torch.cuda.is_available(), task=task)
        if callback and "segments" in result:
            for segment in result["segments"]:
                callback(segment)
        
        # Standard whisper result already has 'language'
        return result

class VoskEngine(BaseEngine):
    def __init__(self, model_size="small"):
        self.model_size = model_size
        self._model = None

    def set_model_size(self, size):
        pass

    @property
    def model(self):
        if self._model is None:
            print("Loading Vosk model...")
            model_path = None
            for item in os.listdir("."):
                if os.path.isdir(item) and "vosk-model" in item:
                    model_path = item
                    break
            
            if not model_path:
                print("Vosk model not found. Using default path 'model'.")
                model_path = "model"
            
            try:
                self._model = vosk.Model(model_path)
            except Exception as e:
                raise RuntimeError(f"Vosk model error: {e}. Please ensure a Vosk model folder is present in the project directory.")
        return self._model

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        rec = vosk.KaldiRecognizer(self.model, 16000)
        rec.SetWords(True)
        
        full_text = ""
        all_segments = []
        
        chunk_size = 4000
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size].tobytes()
            if rec.AcceptWaveform(chunk):
                res = json.loads(rec.Result())
                text = res.get("text", "")
                if text:
                    full_text += text + " "
                    seg = {"text": text, "start": i/16000.0, "end": (i+chunk_size)/16000.0}
                    all_segments.append(seg)
                    if callback: callback(seg)
        
        res = json.loads(rec.FinalResult())
        text = res.get("text", "")
        if text:
            full_text += text
            seg = {"text": text, "start": len(audio_data)/16000.0 - 1, "end": len(audio_data)/16000.0}
            all_segments.append(seg)
            if callback: callback(seg)
            
        return {"text": full_text.strip(), "segments": all_segments}

class StableTSEngine(BaseEngine):
    """Uses stable-ts for better timestamps and less hallucination."""
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def set_model_size(self, size):
        if size != self.model_size:
            self.model_size = size
            self._model = None

    @property
    def model(self):
        if stable_whisper is None:
            raise ImportError("stable-ts not installed. Run: pip install stable-ts")
        if self._model is None:
            print(f"Loading Stable-TS (Faster-Backend) model: {self.model_size}...")
            # Use faster-whisper backend for significantly better performance on 920M
            try:
                self._model = stable_whisper.load_faster_whisper(self.model_size, device=self.device)
            except Exception:
                # Fallback to standard if faster-whisper backend fails
                self._model = stable_whisper.load_model(self.model_size, device=self.device)
        return self._model

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        audio_float = audio_data.astype(np.float32) / 32768.0
        result = self.model.transcribe(audio_float, task=task)
        # stable-ts result is an object, convert to dict-like
        segments = []
        for s in result.segments:
            seg = {"text": s.text, "start": s.start, "end": s.end}
            segments.append(seg)
            if callback: callback(seg)
        return {"text": result.text, "segments": segments}

class AssemblyAIEngine(BaseEngine):
    """Premium Cloud API for high-accuracy transcription."""
    def __init__(self, api_key=None):
        self.api_key = api_key

    def set_model_size(self, size):
        pass

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        if aai is None:
            raise ImportError("assemblyai not installed. Run: pip install assemblyai")
        if not self.api_key:
            raise ValueError("AssemblyAI API Key is required.")
        
        aai.settings.api_key = self.api_key
        
        # Save to temp wav for upload
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            import wave
            with wave.open(tf.name, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data.tobytes())
            temp_path = tf.name

        try:
            transcriber = aai.Transcriber()
            config = aai.TranscriptionConfig(language_detection=True)
            transcript = transcriber.transcribe(temp_path, config=config)
            
            if transcript.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"AssemblyAI Error: {transcript.error}")

            segments = []
            sentences = transcript.get_sentences()
            for s in sentences:
                seg = {"text": s.text, "start": s.start / 1000.0, "end": s.end / 1000.0}
                segments.append(seg)
                if callback: callback(seg)

            return {"text": transcript.text, "segments": segments}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

class GroqEngine(BaseEngine):
    """Ultra-fast Cloud Whisper (Large-v3)."""
    def __init__(self, api_key=None):
        self.api_key = api_key

    def set_model_size(self, size):
        pass

    def transcribe(self, audio_data, callback=None, task="transcribe"):
        if Groq is None:
            raise ImportError("groq not installed. Run: pip install groq")
        if not self.api_key:
            raise ValueError("Groq API Key is required.")
        
        client = Groq(api_key=self.api_key)
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            import wave
            with wave.open(tf.name, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data.tobytes())
            temp_path = tf.name

        try:
            with open(temp_path, "rb") as file:
                # Always use verbose_json to get segment-level data for subtitles
                if task == "translate":
                    response = client.audio.translations.create(
                        file=(temp_path, file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json"
                    )
                else:
                    response = client.audio.transcriptions.create(
                        file=(temp_path, file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json"
                    )
                
                segments = []
                # Safely handle segments (could be dicts or objects depending on SDK version)
                raw_segments = getattr(response, 'segments', [])
                for s in raw_segments:
                    # Extract values safely
                    text = s.get('text', '') if isinstance(s, dict) else getattr(s, 'text', '')
                    start = s.get('start', 0.0) if isinstance(s, dict) else getattr(s, 'start', 0.0)
                    end = s.get('end', 0.0) if isinstance(s, dict) else getattr(s, 'end', 0.0)
                    
                    seg = {"text": text, "start": start, "end": end}
                    segments.append(seg)
                    if callback: callback(seg)
                    
                return {"text": response.text, "segments": segments}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

# --- UI Logic: Modern Application ---

class VideoToTextApp(ctk.CTk):
    """Modern UI for the Video to Text Transcriber."""
    
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Video to Text Transcriber")
        self.geometry("600x600")
        
        # Set Window Icon
        if os.path.exists("app_icon.ico"):
            try:
                self.iconbitmap("app_icon.ico")
            except Exception:
                pass

        ctk.set_appearance_mode("dark")  # Options: "System", "Light", "Dark"
        ctk.set_default_color_theme("blue")  # Options: "blue", "green", "dark-blue"

        # Engine Initialization
        self.engines = {
            "Faster-Whisper": FasterWhisperEngine(),
            "Standard Whisper": StandardWhisperEngine(),
            "Stable-TS (Precision)": StableTSEngine(),
            "Vosk (Offline/Fast)": VoskEngine(),
            "AssemblyAI (Cloud)": AssemblyAIEngine(),
            "Groq (Cloud/Fast)": GroqEngine()
        }
        self.active_engine_name = "Groq (Cloud/Fast)"
        self.config_file = "config.json"
        self.settings = self.load_settings()

        # UI Elements
        self.setup_ui()

    def load_settings(self):
        """Loads saved settings (like API keys) from a JSON file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    if "api_keys" not in data:
                        data["api_keys"] = {}
                    return data
            except Exception:
                pass
        return {"api_keys": {}}

    def save_settings(self):
        """Saves current settings to a JSON file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def setup_ui(self):
        """Initializes the layout and widgets."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1) # Allow the textbox to expand

        # Title/Instruction
        self.lbl_title = ctk.CTkLabel(self, text="AI Video to Text", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Engine & Model Selection Frame
        self.frame_settings = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_settings.grid(row=1, column=0, padx=20, pady=5)
        
        self.lbl_engine = ctk.CTkLabel(self.frame_settings, text="Engine:", font=ctk.CTkFont(size=13))
        self.lbl_engine.pack(side="left", padx=5)
        
        self.combo_engine = ctk.CTkComboBox(self.frame_settings, 
                                           values=list(self.engines.keys()), 
                                           command=self.handle_engine_change,
                                           width=180)
        self.combo_engine.set(self.active_engine_name)
        self.combo_engine.pack(side="left", padx=5)

        self.lbl_model = ctk.CTkLabel(self.frame_settings, text="Size:", font=ctk.CTkFont(size=13))
        self.lbl_model.pack(side="left", padx=5)
        
        self.combo_model = ctk.CTkComboBox(self.frame_settings, 
                                           values=["tiny", "base", "small", "medium", "large", "large-v3", "turbo"], 
                                           command=self.handle_model_change,
                                           width=100)
        self.combo_model.set("base")
        self.combo_model.pack(side="left", padx=5)

        # API Key Field (Hidden by default)
        self.frame_api = ctk.CTkFrame(self, fg_color="transparent")
        self.lbl_api = ctk.CTkLabel(self.frame_api, text="API Key:", font=ctk.CTkFont(size=13))
        self.lbl_api.pack(side="left", padx=5)
        self.entry_api = ctk.CTkEntry(self.frame_api, placeholder_text="Enter API Key here...", width=250, show="*")
        self.entry_api.pack(side="left", padx=5)
        # frame_api is NOT packed yet, we'll pack it when needed

        # Options Frame (Translation & Burning)
        self.frame_options = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_options.grid(row=2, column=0, padx=20, pady=5)

        self.check_translate = ctk.CTkCheckBox(self.frame_options, text="Translate to English")
        self.check_translate.pack(side="left", padx=10)

        self.check_burn = ctk.CTkCheckBox(self.frame_options, text="Burn subtitles")
        self.check_burn.pack(side="left", padx=10)

        # Main Action Button
        self.btn_select = ctk.CTkButton(self, text="Start Transcribe", 
                                        command=self.handle_select_file,
                                        height=45, corner_radius=10,
                                        font=ctk.CTkFont(size=15, weight="bold"))
        self.btn_select.grid(row=3, column=0, padx=20, pady=10)

        # Detected Language Display
        self.lbl_lang = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12, slant="italic"), text_color="gray")
        self.lbl_lang.grid(row=4, column=0, padx=20, pady=0)

        # Live Transcript Textbox
        self.textbox = ctk.CTkTextbox(self, height=200, corner_radius=10)
        self.textbox.grid(row=5, column=0, padx=20, pady=10, sticky="nsew")
        self.textbox.insert("0.0", "Transcription will appear here...")

        # Status & Progress
        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", text_color="#2ecc71") # Greenish
        self.lbl_status.grid(row=6, column=0, padx=20, pady=5)

        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", mode="indeterminate")
        self.progress_bar.grid(row=7, column=0, padx=20, pady=10)
        self.progress_bar.set(0) # Initially empty
        self.progress_bar.grid_forget()

        # Apply initial engine UI state
        self.handle_engine_change(self.active_engine_name)

    def handle_engine_change(self, value):
        """Updates the active engine and adjusts UI options."""
        self.active_engine_name = value
        
        # Show/Hide Model Selector
        if value in ["Faster-Whisper", "Standard Whisper", "Stable-TS (Precision)"]:
            self.lbl_model.pack(side="left", padx=5)
            self.combo_model.pack(side="left", padx=5)
            self.combo_model.configure(state="normal")
        else:
            self.lbl_model.pack_forget()
            self.combo_model.pack_forget()

        # Show/Hide API Key field
        if "Cloud" in value:
            self.frame_api.grid(row=2, column=0, padx=20, pady=5)
            # Auto-fill saved key
            saved_key = self.settings.get("api_keys", {}).get(value, "")
            self.entry_api.delete(0, "end")
            self.entry_api.insert(0, saved_key)
            
            # Push other frames down
            self.frame_options.grid(row=3, column=0, padx=20, pady=5)
            self.btn_select.grid(row=4, column=0, padx=20, pady=10)
        else:
            self.frame_api.grid_forget()
            self.frame_options.grid(row=2, column=0, padx=20, pady=5)
            self.btn_select.grid(row=3, column=0, padx=20, pady=10)

        self.update_status(f"Engine set to {value}", "cyan")

    def handle_model_change(self, value):
        """Updates the active engine model size."""
        self.engines[self.active_engine_name].set_model_size(value)
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
        self.check_translate.configure(state="disabled")
        self.lbl_lang.configure(text="")
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", "Starting transcription...")
        self.progress_bar.grid(row=7, column=0, padx=20, pady=10)
        self.progress_bar.start()
        self.update_status("Processing... Please wait.", "yellow")

        # Background Execution
        should_burn = self.check_burn.get()
        should_translate = self.check_translate.get()
        task = "translate" if should_translate else "transcribe"
        
        thread = threading.Thread(target=self.process_video_task, 
                                  args=(file_path, should_burn, task), 
                                  daemon=True)
        thread.start()

    def get_api_key(self):
        """Retrieves the API key from the entry field."""
        return self.entry_api.get().strip()

    def process_video_task(self, video_path, should_burn, task):
        """The worker method running in a separate thread."""
        try:
            engine = self.engines[self.active_engine_name]
            
            # Set API Key for cloud engines and SAVE it
            if hasattr(engine, "api_key"):
                key = self.get_api_key()
                engine.api_key = key
                if key:
                    self.settings["api_keys"][self.active_engine_name] = key
                    self.save_settings()
            
            self.update_status("Extracting audio...", "cyan")
            audio_data = engine.extract_audio(video_path)
            
            self.update_status(f"Transcribing ({self.active_engine_name})...", "orange")
            result = engine.transcribe(audio_data, callback=self.engine_callback, task=task)
            
            # Update detected language in UI
            if "language" in result:
                lang = result["language"]
                prob = result.get("language_probability", 1.0)
                lang_text = f"Detected Language: {lang} ({prob:.1%})"
                self.after(0, lambda: self.lbl_lang.configure(text=lang_text))

            # Switch back to main thread for UI/Dialogs
            self.after(0, lambda: self.finish_processing(video_path, result, should_burn))
            
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self.handle_error(error_msg))

    def finish_processing(self, video_path, result, should_burn):
        """Cleans up UI and prompts to save."""
        engine = self.engines[self.active_engine_name]
        self.progress_bar.stop()
        self.progress_bar.grid_forget()
        self.btn_select.configure(state="normal")
        self.combo_model.configure(state="normal")
        self.combo_engine.configure(state="normal")
        self.check_burn.configure(state="normal")
        self.check_translate.configure(state="normal")
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
                content = engine.generate_srt(segments)
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
        engine = self.engines[self.active_engine_name]
        output_video = filedialog.asksaveasfilename(
            title="Save Subtitled Video",
            initialfile=f"{suggested_name}_subtitled.mp4",
            filetypes=(("MP4 Video", "*.mp4"), ("All files", "*.*"))
        )

        if output_video:
            # We need the SRT content in a file for FFmpeg to read
            srt_content = engine.generate_srt(segments)
            
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
                        engine.burn_subtitles(video_path, temp_srt_path, output_video)
                        self.after(0, lambda: messagebox.showinfo("Success", f"Video saved successfully to:\n{output_video}"))
                        self.update_status("Video Complete!", "#2ecc71")
                    finally:
                        # Clean up the temp file
                        if os.path.exists(temp_srt_path):
                            os.remove(temp_srt_path)
                except Exception as e:
                    error_msg = str(e)
                    self.after(0, lambda: self.handle_error(error_msg))
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
