"""Configuration du pipeline, chargée depuis les variables d'environnement.

v2 « scraping pur » : plus d'API d'IA ni de courriel — il ne reste que
l'accès Google Sheets et quelques réglages du collecteur.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

FUSEAU_HORAIRE = ZoneInfo("America/Toronto")
RACINE = Path(__file__).resolve().parent.parent
FICHIER_SOURCES = RACINE / "sources.json"
DOSSIER_SORTIE = RACINE / "sortie"


def _env(nom: str, defaut: str | None = None) -> str | None:
    valeur = os.environ.get(nom, "").strip()
    return valeur or defaut


@dataclass(frozen=True)
class Config:
    jours_retention_expires: int
    delai_entre_requetes_s: float
    sheet_id: str | None
    compte_service_brut: str | None
    compte_service_fichier: str | None
    # Passerelle Apps Script (alternative au compte de service — voir appscript/Code.gs)
    appscript_url: str | None
    appscript_jeton: str | None
    # Classeur manuel (2e Google Sheet, organisé par onglets de catégories) :
    # même Code.gs, déployé dans le classeur — voir veille/classeur.py.
    classeur_appscript_url: str | None = None
    classeur_appscript_jeton: str | None = None

    @property
    def url_feuille(self) -> str | None:
        if not self.sheet_id:
            return None
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"

    def infos_compte_service(self) -> dict | None:
        """Retourne la clé JSON du compte de service Google (brute, base64 ou fichier)."""
        if self.compte_service_brut:
            brut = self.compte_service_brut
            if not brut.lstrip().startswith("{"):
                brut = base64.b64decode(brut).decode("utf-8")
            return json.loads(brut)
        if self.compte_service_fichier:
            return json.loads(Path(self.compte_service_fichier).read_text(encoding="utf-8"))
        return None


def charger_config() -> Config:
    return Config(
        jours_retention_expires=int(_env("JOURS_RETENTION_EXPIRES", "90")),
        delai_entre_requetes_s=float(_env("DELAI_ENTRE_REQUETES_S", "1.0")),
        sheet_id=_env("SHEET_ID"),
        compte_service_brut=_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
        compte_service_fichier=_env("GOOGLE_SERVICE_ACCOUNT_FILE"),
        appscript_url=_env("APPSCRIPT_URL"),
        appscript_jeton=_env("APPSCRIPT_TOKEN"),
        classeur_appscript_url=_env("CLASSEUR_APPSCRIPT_URL"),
        classeur_appscript_jeton=_env("CLASSEUR_APPSCRIPT_TOKEN"),
    )


def ouvrir_feuille(config: Config):
    """Choisit le canal d'écriture du Sheet : passerelle Apps Script si configurée,
    sinon compte de service Google (gspread)."""
    if config.appscript_url:
        from .feuille_appscript import FeuilleAppScript

        return FeuilleAppScript(config)
    from .feuille import Feuille

    return Feuille(config)
