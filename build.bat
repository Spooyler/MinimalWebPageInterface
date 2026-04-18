@echo off
REM Build a standalone Windows .exe with PyInstaller.
REM Output: dist\WebPageManager.exe

call .venv\Scripts\activate.bat

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "WebPageManager" ^
    --add-data "ui;ui" ^
    --collect-all webview ^
    main.py

echo.
echo Build complete. Exe at: dist\WebPageManager.exe
