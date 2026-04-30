@echo off
echo ==========================================
echo Flet Android Build Script
echo ==========================================

:: Activate venv if it exists
if exist venv\Scripts\activate (
    echo Activating virtual environment...
    call venv\Scripts\activate
)

:: Check for Android SDK
if "%ANDROID_HOME%"=="" (
    echo [!] ANDROID_HOME is not set. Please install Android SDK and set the variable.
    echo Default path is usually: %LOCALAPPDATA%\Android\Sdk
    pause
    exit /b 1
)

:: Check if flet is installed
python -c "import flet" 2>nul
if %errorlevel% neq 0 (
    echo Flet not found. Installing...
    pip install flet
)

:: Navigate to mobile_src
cd mobile_src

:: Run the build
echo Starting Flet build for APK...
echo Note: This may take a while and will download Flutter/Android SDK if not present.
flet build apk

echo ==========================================
echo Build process finished. 
echo Check the 'build/apk' directory for your file.
echo ==========================================
pause
