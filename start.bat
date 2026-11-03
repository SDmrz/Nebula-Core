
@echo off
title NEBULA CORE - Launcher
cd /d "%~dp0"

echo ========================================
echo          NEBULA CORE LAUNCHER
echo ========================================
echo.

echo [1/3] Recherche des mises a jour...
git pull --ff-only origin main

if errorlevel 1 (
    echo.
    echo [ERREUR] Mise a jour impossible.
    echo Verifie Git ou ta connexion Internet.
    pause
    exit /b 1
)

echo.
echo [2/3] Verification des dependances...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERREUR] Installation des dependances.
    pause
    exit /b 1
)

echo.
echo [3/3] Demarrage de NEBULA CORE...
python app.py

pause
