#!/usr/bin/env bash
set -Eeuo pipefail

# Veille des subventions - lancement Linux/cPanel.
#
# Utilisation :
#   ./lancer_veille.sh        exécute la veille complète
#   ./lancer_veille.sh init   initialise le Google Sheet une seule fois
#
# Prérequis :
#   - Python 3.11+
#   - fichier .env rempli (SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE)

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$RACINE/.venv"
PYTHON_VENV="$VENV/bin/python"
JOURNAUX="$RACINE/journaux"

mkdir -p "$JOURNAUX"

trouver_python() {
    for candidat in python3.12 python3.11 python3 python; do
        if command -v "$candidat" >/dev/null 2>&1; then
            "$candidat" - <<'PY' >/dev/null 2>&1 && {
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
                command -v "$candidat"
                return 0
            }
        fi
    done

    echo "[erreur] Python 3.11+ introuvable." >&2
    echo "         Dans cPanel, activez Python 3.11+ ou demandez-le à l'hébergeur." >&2
    return 1
}

cd "$RACINE"
echo "================= $(date '+%Y-%m-%d %H:%M:%S') ================="

if [ ! -x "$PYTHON_VENV" ]; then
    PYTHON_EXE="$(trouver_python)"
    echo "[config] Python : $PYTHON_EXE"
    echo "[config] Création de l'environnement virtuel .venv..."
    "$PYTHON_EXE" -m venv "$VENV"
fi

if ! "$PYTHON_VENV" -c "import veille, requests, bs4, gspread, pydantic, dateutil" >/dev/null 2>&1; then
    echo "[config] Installation des dépendances..."
    "$PYTHON_VENV" -m pip install --quiet --upgrade pip
    "$PYTHON_VENV" -m pip install --quiet -e "$RACINE"
fi

if [ ! -f "$RACINE/.env" ]; then
    cp "$RACINE/.env.example" "$RACINE/.env"
    echo "[config] Fichier .env créé à partir de .env.example."
    echo "         Renseignez SHEET_ID et GOOGLE_SERVICE_ACCOUNT_FILE, puis relancez."
    exit 1
fi

set -a
# shellcheck disable=SC1091
. "$RACINE/.env"
set +a

if [ -z "${SHEET_ID:-}" ]; then
    echo "[erreur] SHEET_ID absent du fichier .env" >&2
    exit 1
fi

if [ "${1:-}" = "init" ]; then
    echo "[init] Initialisation du Google Sheet (onglets + mise en forme)..."
    "$PYTHON_VENV" scripts/initialiser_feuille.py
    exit $?
fi

if "$PYTHON_VENV" -m veille.main; then
    CODE=0
else
    CODE=$?
fi

if [ "$CODE" -eq 0 ]; then
    echo "[ok] Veille terminée - consultez le Google Sheet."
else
    echo "[erreur] La veille s'est terminée avec le code $CODE - voir les messages ci-dessus." >&2
fi

find "$JOURNAUX" -name 'veille-*.log' -type f -mtime +60 -delete 2>/dev/null || true
exit "$CODE"
