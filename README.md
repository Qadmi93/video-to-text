# VideoToText (Python + Flet + AI)

A cross-platform (Windows & Android) application for transcribing video and audio files into text and subtitles using local ML models (Whisper, Vosk) and Cloud APIs (Groq, AssemblyAI).

## 🚀 Features
- **Multi-Engine Transcription:** Choose between local Faster-Whisper, Standard Whisper, Vosk, or high-speed Cloud APIs like Groq.
- **Mobile Optimized:** Built with Flet (Flutter backend) for a smooth mobile experience on Android.
- **Subtitle Generation:** Automatically generates `.srt` and `.txt` files from your media.
- **Cross-Platform:** Works on Desktop (CustomTkinter) and Mobile (Flet/Flutter).

## 🛠 Tech Stack
- **Language:** Python
- **UI Frameworks:** Flet (Mobile), CustomTkinter (Desktop)
- **Transcription Engines:** Faster-Whisper, Groq (Whisper-v3), Vosk, AssemblyAI
- **Video Processing:** FFmpeg

## 📱 Mobile Build (Android)
To build the Android APK, use the included `build_android.bat`. This script:
1. Sets up a local persistent Flutter SDK.
2. Manages Python dependencies in a virtual environment.
3. Injects FFmpeg as a native library to bypass Android security restrictions.

---
*Note: This project is part of an AI-assisted learning journey transitioning from Java/XML Android development to modern Python/AI-driven software engineering.*
