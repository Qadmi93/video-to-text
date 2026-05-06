@echo off
setlocal
echo ==========================================
echo Optimized Flet Android Build Script
echo ==========================================

:: 1. SET PERSISTENT PATHS (Survives session resets)
:: We use a local folder so the 500MB+ download isn't lost when the session resets
set "LOCAL_CACHE=%~dp0.flet_cache"
if not exist "%LOCAL_CACHE%" mkdir "%LOCAL_CACHE%"

:: Force Flet to store its Flutter SDK inside your project folder
set "FLET_FLUTTER_SDK_PATH=%LOCAL_CACHE%\flutter"
set "PUB_CACHE=%LOCAL_CACHE%\pub"

:: 2. LINK ANDROID STUDIO SDK & JAVA
:: Using your local Android Studio install to avoid redownloading tools
set "ANDROID_HOME=C:\Users\home\AppData\Local\Android\Sdk"
set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"

:: Add tools to PATH
set "PATH=%ANDROID_HOME%\platform-tools;%JAVA_HOME%\bin;%LOCAL_CACHE%\flutter\bin;%PATH%"

echo [i] Using Android SDK: %ANDROID_HOME%
echo [i] Using Java: %JAVA_HOME%
echo [i] Using Persistent Cache: %LOCAL_CACHE%

:: 3. ACTIVATE ENVIRONMENT
if exist venv\Scripts\activate (
    echo Activating virtual environment...
    call venv\Scripts\activate
)

:: Check if flet is installed
python -c "import flet" 2>nul
if %errorlevel% neq 0 (
    echo [!] Flet not found. Installing into venv...
    pip install flet
)

:: 4. RUN BUILD
:: Navigate to where the mobile source code lives
if exist mobile_src (
    cd mobile_src
)

echo Starting Flet build for APK...
echo This will use the persistent cache in .flet_cache.
echo Compiling a universal APK for maximum device compatibility (32-bit & 64-bit)...
flet build apk --yes --flutter-build-args="--target-platform=android-arm,android-arm64,android-x64"

echo ==========================================
echo Build process finished. 
echo Check the 'mobile_src/build/apk' directory for your file.
echo ==========================================
pause
