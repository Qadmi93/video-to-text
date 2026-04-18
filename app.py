import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import whisper
import imageio_ffmpeg
import subprocess
import numpy as np

def extract_audio_from_video(video_path):
    """Extracts audio from video and returns it as a 16kHz mono numpy array for Whisper."""
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
    
    # Open ffmpeg process with a pipe for stdout
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    audio_chunks = []
    chunk_size = 4096  # Read 4KB at a time
    
    while True:
        block = process.stdout.read(chunk_size)
        if not block:
            break
        audio_chunks.append(np.frombuffer(block, np.int16))
        
    # Wait for process to finish and check for errors
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")

    # Combine chunks and convert to float32 normalized for Whisper
    return np.concatenate(audio_chunks).astype(np.float32) / 32768.0

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Video to Text Transcriber")
        self.root.geometry("450x250")
        self.root.resizable(False, False)
        
        self.lbl_instruction = tk.Label(root, text="Select an MP4 video to generate a text transcript.", pady=15)
        self.lbl_instruction.pack()
        
        self.btn_select = tk.Button(root, text="Start Transcribe", bg="blue", fg="white", command=self.select_file, width=20, height=2)
        self.btn_select.pack(pady=20)
        
        self.lbl_status = tk.Label(root, text="Status: Ready.", fg="green")
        self.lbl_status.pack(pady=10)
        
        self.progress = ttk.Progressbar(root, orient="horizontal", length=300, mode="indeterminate")
        
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Video",
            filetypes=(("MP4 files", "*.mp4"), ("All files", "*.*"))
        )
        if file_path:
            self.lbl_status.config(text="Status: Setting up environment...", fg="blue")
            self.btn_select.config(state=tk.DISABLED)
            self.progress.pack(pady=10)
            self.progress.start(10)
            
            # Use a background thread so the app doesn't freeze
            threading.Thread(target=self.process_video, args=(file_path,), daemon=True).start()

    def process_video(self, video_path):
        try:
            self.root.after(0, lambda: self.lbl_status.config(text="Status: Extracting audio from video..."))
            audio_array = extract_audio_from_video(video_path)
            
            self.root.after(0, lambda: self.lbl_status.config(text="Status: Transcribing audio (this may take a minute)..."))
            # Loading base model is quick
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = whisper.load_model("base", device=device)
            result = model.transcribe(audio_array, fp16=torch.cuda.is_available())
            
            transcript = result["text"].strip()
            self.root.after(0, lambda: self.save_transcript(video_path, transcript))
            
        except Exception as e:
            self.root.after(0, lambda: self.show_error(str(e)))
            
    def save_transcript(self, video_path, transcript):
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_select.config(state=tk.NORMAL)
        self.lbl_status.config(text="Status: Transcription finished!", fg="green")
        
        suggested_filename = os.path.basename(video_path)
        suggested_filename = os.path.splitext(suggested_filename)[0] + ".txt"
        
        save_path = filedialog.asksaveasfilename(
            title="Save Transcript",
            initialfile=suggested_filename,
            defaultextension=".txt",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )
        
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            messagebox.showinfo("Success", "Transcript saved successfully!")
        else:
            messagebox.showwarning("Cancelled", "Transcript was not saved.")
            
    def show_error(self, error_message):
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_select.config(state=tk.NORMAL)
        self.lbl_status.config(text="Status: Error encountered.", fg="red")
        messagebox.showerror("Error", f"An error occurred:\n{error_message}")

if __name__ == "__main__":
    # Ensure crisp text rendering on Windows displays
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
        
    root = tk.Tk()
    app = App(root)
    root.mainloop()
