@echo off
REM Builds a standalone RICE-DL.exe with PyInstaller.
REM Run this on Windows, inside the project folder, with Python installed.

python -m pip install --upgrade pyinstaller
pyinstaller --onefile --noconsole --name RICE-DL main.py

echo.
echo Build complete. Find RICE-DL.exe in the "dist" folder.
echo Copy yt-dlp.exe (and ffmpeg.exe, if you use it) into that same
echo folder, or point the app at them from the SETTINGS tab.
pause
