@echo off
REM ============================================================================
REM  Veille des subventions - lancement local sous Windows
REM
REM  Ce script fait tout :
REM    1. cree la tache planifiee quotidienne dans le Planificateur de taches
REM    2. verifie que Python est installe (sinon : installation via winget)
REM    3. cree l'environnement virtuel et installe les dependances si besoin
REM    4. execute la veille (python -m veille.main)
REM
REM  Utilisation :
REM    - double-clic                 : installation complete + execution immediate
REM    - lancer_veille.bat init      : initialise le Google Sheet (une seule fois)
REM    - lancer_veille.bat tache     : mode silencieux (utilise par la tache planifiee,
REM                                    sortie redirigee vers journaux\veille-AAAA-MM-JJ.log)
REM
REM  Reglages : HEURE et NOM_TACHE ci-dessous.
REM  Prerequis : fichier .env rempli - APPSCRIPT_URL + APPSCRIPT_TOKEN (recommande)
REM              ou SHEET_ID + GOOGLE_SERVICE_ACCOUNT_FILE (compte de service).
REM  Desinstaller la planification : schtasks /Delete /TN VeilleSubventions /F
REM ============================================================================
setlocal EnableExtensions
chcp 65001 >nul

REM ----- Reglages -------------------------------------------------------------
set "HEURE=07:00"
set "NOM_TACHE=VeilleSubventions"

REM ----- Chemins ---------------------------------------------------------------
set "RACINE=%~dp0"
set "VENV=%RACINE%.venv-windows"
set "PYTHON_VENV=%VENV%\Scripts\python.exe"
set "JOURNAUX=%RACINE%journaux"
set "PYTHONUTF8=1"

if not exist "%JOURNAUX%" mkdir "%JOURNAUX%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "JOUR=%%i"

REM Mode tache planifiee : tout part dans le journal du jour, sans fenetre bloquante.
if /i "%~1"=="tache" (
    call :executer tache >> "%JOURNAUX%\veille-%JOUR%.log" 2>&1
    exit /b %errorlevel%
)

REM Mode interactif (double-clic ou "init") : sortie a l'ecran, pause a la fin.
call :executer %1
echo.
pause
exit /b


REM ============================================================================
:executer
echo ================= %date% %time% =================

REM --- 1. Tache planifiee quotidienne -----------------------------------------
schtasks /Query /TN "%NOM_TACHE%" >nul 2>&1
if errorlevel 1 (
    echo [config] Creation de la tache planifiee "%NOM_TACHE%" - tous les jours a %HEURE%
    schtasks /Create /TN "%NOM_TACHE%" /TR "\"%~f0\" tache" /SC DAILY /ST %HEURE% /F >nul
    if errorlevel 1 (
        echo [attention] Echec de la creation de la tache planifiee.
        echo              La veille fonctionnera quand meme en lancement manuel.
    )
)

REM --- 2. Python + environnement virtuel ---------------------------------------
if exist "%PYTHON_VENV%" goto :venv_ok
call :trouver_python || exit /b 1
echo [config] Creation de l'environnement virtuel .venv-windows...
"%PYTHON_EXE%" -m venv "%VENV%" || exit /b 1
:venv_ok

REM --- 3. Dependances (repare aussi une installation interrompue) --------------
"%PYTHON_VENV%" -c "import veille, requests, bs4, gspread, pydantic, dateutil" >nul 2>&1
if errorlevel 1 (
    echo [config] Installation des dependances...
    "%PYTHON_VENV%" -m pip install --quiet --upgrade pip
    "%PYTHON_VENV%" -m pip install --quiet -e "%RACINE%." || exit /b 1
)

REM --- 4. Configuration (.env) ---------------------------------------------------
if not exist "%RACINE%.env" (
    copy "%RACINE%.env.example" "%RACINE%.env" >nul
    echo [config] Fichier .env cree a partir de .env.example.
    echo          Renseignez SHEET_ID et GOOGLE_SERVICE_ACCOUNT_FILE, puis relancez.
    exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%RACINE%.env") do set "%%a=%%b"
if not defined SHEET_ID if not defined APPSCRIPT_URL (
    echo [erreur] Ni APPSCRIPT_URL ni SHEET_ID dans le fichier .env
    echo          Option recommandee : APPSCRIPT_URL + APPSCRIPT_TOKEN - voir GUIDE.md
    exit /b 1
)

REM --- 5. Execution ---------------------------------------------------------------
cd /d "%RACINE%"
if /i "%~1"=="init" (
    echo [init] Initialisation du Google Sheet ^(onglets + mise en forme^)...
    "%PYTHON_VENV%" scripts\initialiser_feuille.py
    exit /b %errorlevel%
)

"%PYTHON_VENV%" -m veille.main
set "CODE=%errorlevel%"
if "%CODE%"=="0" (
    echo [ok] Veille terminee - consultez le Google Sheet.
) else (
    echo [erreur] La veille s'est terminee avec le code %CODE% - voir les messages ci-dessus.
)

REM Menage : journaux de plus de 60 jours.
forfiles /P "%JOURNAUX%" /M veille-*.log /D -60 /C "cmd /c del @path" >nul 2>&1
exit /b %CODE%


REM ============================================================================
REM Localise un Python 3 utilisable dans PYTHON_EXE ; l'installe au besoin.
:trouver_python
set "PYTHON_EXE="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
if defined PYTHON_EXE goto :python_ok
for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
if defined PYTHON_EXE goto :python_ok

echo [config] Python introuvable - installation via winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo [erreur] winget indisponible sur ce poste.
    echo          Installez Python 3.12+ depuis https://www.python.org/downloads/
    echo          ^(cochez "Add python.exe to PATH"^) puis relancez ce script.
    exit /b 1
)
winget install --id Python.Python.3.12 -e --source winget --silent --accept-package-agreements --accept-source-agreements
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
if defined PYTHON_EXE goto :python_ok
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PYTHON_EXE goto :python_ok

echo [erreur] Python vient d'etre installe mais n'est pas encore visible dans cette
echo          session. Fermez cette fenetre et relancez le script.
exit /b 1

:python_ok
echo [ok] Python : %PYTHON_EXE%
exit /b 0
