try:
    from faster_whisper import WhisperModel
    print("Success: faster-whisper imported")
except ImportError as e:
    print(f"Error: {e}")
