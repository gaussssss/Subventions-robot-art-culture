"""Initialise le Google Sheet : onglets, en-têtes, gel de la ligne 1 et mise en
forme conditionnelle (section 3.3 des spécifications).

À exécuter une fois après la création de la feuille :
    python scripts/initialiser_feuille.py

Ré-exécutable sans danger : les règles conditionnelles existantes sont remplacées.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from veille.config import charger_config  # noqa: E402
from veille.feuille import ONGLET_SUBVENTIONS, Feuille  # noqa: E402
from veille.models import COLONNES  # noqa: E402

logger = logging.getLogger("initialiser_feuille")

VERT = {"red": 0.85, "green": 0.94, "blue": 0.83}      # lignes « Nouveau »
ORANGE = {"red": 0.99, "green": 0.90, "blue": 0.80}    # date limite ≤ 14 jours
GRIS = {"red": 0.94, "green": 0.94, "blue": 0.94}      # lignes « Expiré »
NB_LIGNES_REGLES = 5000

# Colonnes (1-indexées) utilisées dans les formules : G = date_limite, J = statut.
_COL_DATE = COLONNES.index("date_limite")       # index 6 → colonne G
_COL_STATUT = COLONNES.index("statut")          # index 9 → colonne J
_LETTRE_DATE = chr(ord("A") + _COL_DATE)
_LETTRE_STATUT = chr(ord("A") + _COL_STATUT)


def _regle(plage: dict, formule: str, fond: dict) -> dict:
    return {
        "addConditionalFormatRule": {
            "index": 0,
            "rule": {
                "ranges": [plage],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": formule}],
                    },
                    "format": {"backgroundColor": fond},
                },
            },
        }
    }


def principal() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    config = charger_config()
    feuille = Feuille(config)
    feuille.assurer_structure()

    onglet = feuille.classeur.worksheet(ONGLET_SUBVENTIONS)
    onglet.format("A1:N1", {"textFormat": {"bold": True}})
    onglet.freeze(rows=1)

    plage_tableau = {
        "sheetId": onglet.id,
        "startRowIndex": 1,
        "endRowIndex": NB_LIGNES_REGLES,
        "startColumnIndex": 0,
        "endColumnIndex": len(COLONNES),
    }
    plage_dates = dict(plage_tableau, startColumnIndex=_COL_DATE, endColumnIndex=_COL_DATE + 1)

    # Idempotence : suppression des règles conditionnelles existantes de l'onglet.
    metadonnees = feuille.classeur.fetch_sheet_metadata()
    nb_existantes = 0
    for feuille_meta in metadonnees.get("sheets", []):
        if feuille_meta.get("properties", {}).get("sheetId") == onglet.id:
            nb_existantes = len(feuille_meta.get("conditionalFormats", []))

    requetes = [
        {"deleteConditionalFormatRule": {"sheetId": onglet.id, "index": 0}}
        for _ in range(nb_existantes)
    ]
    # L'ordre compte (première règle gagnante par cellule) :
    # 1. dates limites à ≤ 14 jours en orange (colonne date seulement) ;
    # 2. lignes « Nouveau » en vert ; 3. lignes « Expiré » en gris.
    formule_orange = (
        f'=IFERROR(AND(${_LETTRE_DATE}2<>"", ${_LETTRE_DATE}2<>"continu", '
        f"DATEVALUE(${_LETTRE_DATE}2)>=TODAY(), "
        f"DATEVALUE(${_LETTRE_DATE}2)-TODAY()<=14), FALSE)"
    )
    requetes.append(_regle(plage_dates, formule_orange, ORANGE))
    requetes.append(_regle(plage_tableau, f'=${_LETTRE_STATUT}2="Nouveau"', VERT))
    requetes.append(_regle(plage_tableau, f'=${_LETTRE_STATUT}2="Expiré"', GRIS))

    feuille.classeur.batch_update({"requests": requetes})
    logger.info(
        "Feuille initialisée : onglets, en-têtes, %d règle(s) remplacée(s), 3 règles créées.",
        nb_existantes,
    )
    logger.info("URL : %s", config.url_feuille)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
