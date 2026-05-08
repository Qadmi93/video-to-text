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
    echo [!] Flet or dependencies not found. Installing into venv...
    pip install flet flet-permission-handler groq

:: 4. RUN BUILD
:: Navigate to where the mobile source code lives
if exist mobile_src (
    cd mobile_src
)

echo Starting Flet build for APK...
echo This will use the persistent cache in .flet_cache.
echo Compiling a universal APK for maximum device compatibility (32-bit and 64-bit)...
flet build apk --yes --compile-packages --flutter-build-args="--target-platform=android-arm,android-arm64,android-x64"

:: --- INJECT FFMPEG AS NATIVE LIBRARY TO BYPASS ANDROID 10+ W^X EXEC RESTRICTION ---
echo [i] Injecting FFmpeg as a native library...
set "APK_PATH=build\apk\video-to-text-mobile.apk"
set "ALIGNED_APK=build\apk\video-to-text-mobile-aligned.apk"
set "TEMP_DIR=build\temp_inject"

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%\lib\arm64-v8a"
copy /y ffmpeg "%TEMP_DIR%\lib\arm64-v8a\libffmpeg.so"

:: Add the lib folder to the APK
"%JAVA_HOME%\bin\jar.exe" uf "%APK_PATH%" -C "%TEMP_DIR%" lib

:: Zipalign the APK
echo [i] Zipaligning the modified APK...
"%ANDROID_HOME%\build-tools\37.0.0\zipalign.exe" -f -p 4 "%APK_PATH%" "%ALIGNED_APK%"

:: Sign the APK using the default debug keystore
echo [i] Signing the modified APK...
call "%ANDROID_HOME%\build-tools\37.0.0\apksigner.bat" sign --ks "%USERPROFILE%\.android\debug.keystore" --ks-pass pass:android --key-pass pass:android "%ALIGNED_APK%"

:: Overwrite the original APK with the injected one
move /y "%ALIGNED_APK%" "%APK_PATH%"
rmdir /s /q "%TEMP_DIR%"
echo [i] FFmpeg injection complete!

echo ==========================================
echo Build process finished. 
echo Check the 'mobile_src/build/apk' directory for your file.
echo ==========================================
pause
