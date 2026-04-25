import os
import requests
import zipfile
import io

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = "vosk-model-small-en-us-0.15"

if not os.path.exists(MODEL_DIR):
    print(f"Downloading Vosk model from {MODEL_URL}...")
    response = requests.get(MODEL_URL)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(".")
        print("Model downloaded and extracted successfully.")
    else:
        print(f"Failed to download model. Status code: {response.status_code}")
else:
    print("Vosk model already exists.")
