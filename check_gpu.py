import torch
import whisper
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
print(f"Device: {'cuda' if torch.cuda.is_available() else 'cpu'}")
