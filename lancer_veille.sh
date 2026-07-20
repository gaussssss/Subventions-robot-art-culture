#!/usr/bin/env bash
set -Eeuo pipefail

# Veille des subventions - lancement Linux/cPanel.
#
# Utilisation :
#   ./lancer_veille.sh             exécute la veille complète
#   ./lancer_veille.sh init        initialise le Google Sheet (une seule fois)
#                                  puis enchaîne la première collecte
#   ./lancer_veille.sh tache       mode silencieux pour le cron (sortie → journaux/)
#   ./lancer_veille.sh planifier   ajoute la tâche au crontab (7 h chaque matin)
#                                  puis enchaîne la première collecte
#
# Sur cPanel sans accès SSH : menu « Tâches Cron », ajouter la commande
#   /bin/bash /home/VOTRECOMPTE/chemin/vers/lancer_veille.sh tache
# avec minute = 0 et heure = 7.
#
# Prérequis :
#   - Python 3.11+ (détecté automatiquement, y compris /opt/alt/... sur cPanel)
#   - fichier .env rempli : APPSCRIPT_URL + APPSCRIPT_TOKEN (recommandé),
#     ou SHEET_ID + GOOGLE_SERVICE_ACCOUNT_FILE (compte de service)

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$RACINE/.venv"
PYTHON_VENV="$VENV/bin/python"
JOURNAUX="$RACINE/journaux"
HEURE_CRON="0 7 * * *"   # minute heure jour mois jour-semaine

mkdir -p "$JOURNAUX"

# Mode cron : toute la sortie part dans le journal du jour.
if [ "${1:-}" = "tache" ]; then
    exec >>"$JOURNAUX/veille-$(date '+%Y-%m-%d').log" 2>&1
fi

trouver_python() {
    local candidat chemin
    for candidat in \
        python3.13 python3.12 python3.11 python3 \
        /opt/alt/python313/bin/python3.13 \
        /opt/alt/python312/bin/python3.12 \
        /opt/alt/python311/bin/python3.11 \
        /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11; do
        chemin="$(command -v "$candidat" 2>/dev/null || true)"
        [ -n "$chemin" ] || continue
        if "$chemin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
            >/dev/null 2>&1; then
            echo "$chemin"
            return 0
        fi
    done

    echo "[erreur] Python 3.11+ introuvable." >&2
    echo "         Dans cPanel, menu « Setup Python App » pour en activer un, ou" >&2
    echo "         demandez à l'hébergeur le chemin (ex. /opt/alt/python312)." >&2
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

if ! "$PYTHON_VENV" -c "import veille, requests, bs4, gspread, pydantic, dateutil, tzdata" >/dev/null 2>&1; then
    echo "[config] Installation des dépendances..."
    "$PYTHON_VENV" -m pip install --quiet --upgrade pip
    "$PYTHON_VENV" -m pip install --quiet -e "$RACINE"
fi

if [ ! -f "$RACINE/.env" ]; then
    cp "$RACINE/.env.example" "$RACINE/.env"
    echo "[config] Fichier .env créé à partir de .env.example."
    echo "         Renseignez APPSCRIPT_URL et APPSCRIPT_TOKEN (ou SHEET_ID +"
    echo "         GOOGLE_SERVICE_ACCOUNT_FILE), puis relancez."
    exit 1
fi

set -a
# shellcheck disable=SC1091
. "$RACINE/.env"
set +a

if [ -z "${APPSCRIPT_URL:-}" ] && [ -z "${SHEET_ID:-}" ]; then
    echo "[erreur] Ni APPSCRIPT_URL ni SHEET_ID dans le fichier .env" >&2
    exit 1
fi

if [ "${1:-}" = "init" ]; then
    echo "[init] Initialisation du Google Sheet (onglets + mise en forme)..."
    "$PYTHON_VENV" scripts/initialiser_feuille.py
    echo "[init] Structure prête — la première collecte démarre tout de suite..."
fi

if [ "${1:-}" = "planifier" ]; then
    LIGNE="$HEURE_CRON /bin/bash $RACINE/lancer_veille.sh tache"
    if ! command -v crontab >/dev/null 2>&1; then
        echo "[attention] crontab indisponible ici. Sur cPanel, menu « Tâches Cron » :" >&2
        echo "            commande : /bin/bash $RACINE/lancer_veille.sh tache" >&2
        echo "            minute 0, heure 7." >&2
        exit 1
    fi
    ( crontab -l 2>/dev/null | grep -v "lancer_veille.sh" || true; echo "$LIGNE" ) | crontab -
    echo "[ok] Tâche cron installée : $LIGNE"
    echo "     (vérifier : crontab -l ; retirer : crontab -e)"
    echo "[config] La première collecte démarre tout de suite..."
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
