@echo off
REM =============================================================
REM test_demucs.bat
REM
REM Script de test pour demucs_separator (Windows).
REM
REM Usage:
REM   test_demucs.bat                    (utilise royalty-free-onlap-the-awakening.mp3 du meme dossier)
REM   test_demucs.bat C:\chemin\vers.mp3 (utilise le fichier audio indique)
REM
REM Variable d'environnement optionnelle :
REM   DEMUCS_BIN   chemin explicite vers l'executable demucs_separator.exe
REM =============================================================

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM -------------------------------------------------------------
REM Fichier audio a traiter
REM -------------------------------------------------------------

if "%~1"=="" (
    set "INPUT_FILE=%SCRIPT_DIR%royalty-free-onlap-the-awakening.mp3"
) else (
    set "INPUT_FILE=%~1"
)

if not exist "!INPUT_FILE!" (
    echo.
    echo ERREUR: Fichier audio introuvable : !INPUT_FILE!
    exit /b 1
)

echo ==^> Fichier audio : !INPUT_FILE!

REM -------------------------------------------------------------
REM Localisation de l'executable demucs_separator.exe
REM -------------------------------------------------------------

set "BIN="

if not "%DEMUCS_BIN%"=="" (
    set "BIN=%DEMUCS_BIN%"
) else (
    if exist "%SCRIPT_DIR%dist/demucs_separator.exe" (
        set "BIN=%SCRIPT_DIR%dist/demucs_separator.exe"
    ) else (
        for %%I in (demucs_separator.exe) do (
            if not "%%~$PATH:I"=="" set "BIN=%%~$PATH:I"
        )
    )
)

if "!BIN!"=="" (
    echo.
    echo ERREUR: Executable demucs_separator.exe introuvable ^(dossier du script ou PATH^).
    echo Definissez la variable DEMUCS_BIN si besoin.
    exit /b 1
)

echo ==^> Executable utilise : !BIN!

REM -------------------------------------------------------------
REM Test de version
REM -------------------------------------------------------------

echo ==^> Verification de la version...

"!BIN!" --version
if errorlevel 1 (
    echo.
    echo ERREUR: echec de "!BIN! --version"
    exit /b 1
)

REM -------------------------------------------------------------
REM Preparation du dossier de sortie
REM -------------------------------------------------------------

set "OUTPUT_DIR=%SCRIPT_DIR%output"

if not exist "!OUTPUT_DIR!" mkdir "!OUTPUT_DIR!"

for %%F in ("!INPUT_FILE!") do set "INPUT_BASENAME=%%~nxF"
set "WORK_FILE=!OUTPUT_DIR!\!INPUT_BASENAME!"

echo ==^> Copie du fichier audio dans : !OUTPUT_DIR!
copy /y "!INPUT_FILE!" "!WORK_FILE!" >nul

REM -------------------------------------------------------------
REM Execution
REM -------------------------------------------------------------

echo.
echo ==^> Lancement de demucs_separator...
echo.

"!BIN!" "!WORK_FILE!"
set "STATUS=%ERRORLEVEL%"

echo.

if not "%STATUS%"=="0" (
    echo ERREUR: demucs_separator a termine avec le code %STATUS%
    exit /b %STATUS%
)

REM -------------------------------------------------------------
REM Fin
REM -------------------------------------------------------------

echo ==^> Traitement termine.
echo.
echo Fichiers produits dans : !OUTPUT_DIR!
dir /b "!OUTPUT_DIR!"

endlocal
