@echo off
setlocal
title NEBULA CORE - Launcher
cd /d "%~dp0"
echo ========================================
echo       NEBULA CORE - LAUNCHER V2.2
echo ========================================
echo.
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
 echo [ERREUR] Lance start.bat depuis le dossier Git clone.
 pause
 exit /b 1
)
echo [1/3] Mise a jour depuis GitHub...
git pull --ff-only
if errorlevel 1 (
 echo [ERREUR] Mise a jour impossible. Verifie git status.
 pause
 exit /b 1
)
echo [2/3] Dependances...
python -m pip install -r requirements.txt
if errorlevel 1 (
 echo [ERREUR] Installation des dependances.
 pause
 exit /b 1
)
if not exist ".env" (
 echo [ERREUR] Fichier .env manquant.
 pause
 exit /b 1
)
echo [3/3] Demarrage du serveur dans une nouvelle fenetre...
start "NEBULA CORE - Serveur" cmd /k "cd /d ""%~dp0"" && python app.py"
echo Attente de la disponibilite du dashboard...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 40;$i++){try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:8765/' -UseBasicParsing -TimeoutSec 2;if($r.StatusCode -eq 200){$ok=$true;break}}catch{};Start-Sleep -Seconds 1};if($ok){Start-Process 'http://127.0.0.1:8765/';exit 0}else{exit 1}"
if errorlevel 1 (
 echo [ERREUR] Dashboard inaccessible. Consulte la fenetre serveur.
 pause
 exit /b 1
)
echo Dashboard ouvert dans le navigateur par defaut.
exit /b 0
