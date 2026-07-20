"""Écriture du Google Sheet via une passerelle Apps Script (sans compte de service).

Alternative à `veille.feuille.Feuille` quand la création d'une clé de compte de
service n'est pas possible : un petit script (appscript/Code.gs) est collé dans
le Sheet et déployé en application Web ; le pipeline lui envoie les données par
HTTP avec un jeton partagé. Même interface publique que `Feuille`.

Configuration (.env) : APPSCRIPT_URL (l'adresse /exec du déploiement) et
APPSCRIPT_TOKEN (la phrase secrète, identique au JETON du script).
"""

from __future__ import annotations

import json
import logging

import requests

from .config import Config
from .models import LigneSubvention

logger = logging.getLogger(__name__)

DELAI_EXPIRATION_S = 180  # l'écriture de ~1000 lignes prend quelques secondes côté Google


class ErreurAppScript(RuntimeError):
    pass


def appeler_passerelle(url: str, jeton: str, action: str, **donnees) -> dict:
    """Envoie une action à une passerelle Apps Script et retourne sa réponse JSON.

    Partagée entre le Sheet du robot (FeuilleAppScript) et le classeur manuel
    (veille.classeur) : même script Code.gs, déployé dans chaque document.
    """
    reponse = requests.post(
        url,
        json={"jeton": jeton, "action": action, **donnees},
        timeout=DELAI_EXPIRATION_S,
        allow_redirects=True,  # Apps Script répond par une redirection vers le résultat
    )
    reponse.raise_for_status()
    try:
        objet = reponse.json()
    except (json.JSONDecodeError, ValueError) as exc:
        # Réponse HTML = presque toujours un déploiement mal configuré.
        raise ErreurAppScript(
            "La passerelle Apps Script n'a pas répondu en JSON. Vérifier que le "
            "déploiement est une « application Web » avec accès « Tout le monde », "
            "et que l'URL est bien l'adresse qui se termine par /exec."
        ) from exc
    if not objet.get("ok"):
        raise ErreurAppScript(f"Passerelle Apps Script : {objet.get('erreur', 'erreur inconnue')}")
    return objet


class FeuilleAppScript:
    def __init__(self, config: Config):
        if not config.appscript_url:
            raise RuntimeError("Configuration Apps Script incomplète : définir APPSCRIPT_URL.")
        if not config.appscript_jeton:
            raise RuntimeError("Configuration Apps Script incomplète : définir APPSCRIPT_TOKEN.")
        self.url = config.appscript_url
        self.jeton = config.appscript_jeton

    def _appeler(self, action: str, **donnees) -> dict:
        return appeler_passerelle(self.url, self.jeton, action, **donnees)

    # ── Interface commune avec veille.feuille.Feuille ─────────────────────────

    def assurer_structure(self) -> None:
        self._appeler("structure")

    def initialiser(self) -> None:
        """Structure + mise en forme conditionnelle (équivalent d'initialiser_feuille)."""
        self._appeler("init")
        logger.info("Feuille initialisée via la passerelle Apps Script.")

    def lire_subventions(self) -> list[LigneSubvention]:
        lignes = self._appeler("lire").get("lignes", [])
        return [
            LigneSubvention.depuis_liste([str(c) for c in rangee])
            for rangee in lignes
            if any(str(cellule).strip() for cellule in rangee)
        ]

    def ecrire_subventions(self, lignes: list[LigneSubvention]) -> None:
        self._appeler("ecrire", lignes=[ligne.en_liste() for ligne in lignes])

    def archiver(self, lignes: list[LigneSubvention], date_archivage: str) -> None:
        if not lignes:
            return
        self._appeler(
            "archiver", lignes=[ligne.en_liste() + [date_archivage] for ligne in lignes]
        )
        logger.info("%d ligne(s) expirée(s) archivée(s)", len(lignes))

    def ajouter_journal(self, valeurs: list[str]) -> None:
        self._appeler("journal", ligne=valeurs)
