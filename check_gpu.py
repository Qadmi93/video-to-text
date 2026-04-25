import torch
import whisper
import sys

print(f"Python version: {sys.version}")
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
    print(f"CUDA Device Count: {torch.cuda.device_count()}")
    print(f"Current Device: {torch.cuda.current_device()}")
    capability = torch.cuda.get_device_capability(0)
    print(f"Compute Capability: {capability[0]}.{capability[1]}")
else:
    print("\n[!] CUDA is NOT available to PyTorch.")
    if "+cpu" in torch.__version__:
        print("Reason: You have the CPU-only version of PyTorch installed.")
    else:
        print("Reason: Drivers might be missing, or your GPU might not be supported by this PyTorch version.")
