@echo off
REM ============================================================
REM build_windows.bat
REM Compile demucs_separator.py en executable autonome (.exe)
REM pour Windows.
REM
REM A executer sur une machine Windows avec Python 3.9+ installe
REM et present dans le PATH.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Build Windows - demucs_separator ===

where python >nul 2>nul
if errorlevel 1 (
    echo ERREUR: python introuvable dans le PATH.
    echo Installez Python 3.9+ depuis https://www.python.org/downloads/
    echo et cochez "Add python.exe to PATH" lors de l'installation.
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo AVERTISSEMENT: ffmpeg n'est pas installe sur cette machine.
    echo Il n'est pas requis pour la compilation, mais SERA requis a l'execution
    echo sur la machine cible ^(voir README.md^).
)

echo [1/4] Creation de l'environnement virtuel de build...
python -m venv build_venv
call build_venv\Scripts\activate.bat

echo [2/4] Installation des dependances...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/4] Compilation avec PyInstaller...
pyinstaller  ^
  --onefile  ^
  --clean  ^
  --noconfirm  ^
  --name demucs_separator  ^
  --collect-all numpy  ^
  --collect-all demucs  ^
  --collect-all torch  ^
  --collect-all torchaudio  ^
  --collect-all torchcodec  ^
  --collect-all julius  ^
  --collect-all openunmix  ^
  --collect-data certifi ^
  demucs_separator.py

call build_venv\Scripts\deactivate.bat

echo [4/4] Termine.
echo.
echo Executable genere : dist\demucs_separator.exe
echo Vous pouvez le copier sur une autre machine Windows compatible (voir README.md).

endlocal
