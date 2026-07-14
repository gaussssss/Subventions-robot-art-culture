"""Lecture et écriture du Google Sheet (gspread, compte de service)."""

from __future__ import annotations

import logging

import google.auth
import gspread
from google.auth import exceptions as erreurs_google_auth

from .config import Config
from .models import COLONNES, COLONNES_ARCHIVES, COLONNES_JOURNAL, LigneSubvention

logger = logging.getLogger(__name__)

ONGLET_SUBVENTIONS = "Subventions"
ONGLET_JOURNAL = "Journal"
ONGLET_ARCHIVES = "Archives"

_DERNIERE_COLONNE = chr(ord("A") + len(COLONNES) - 1)  # « N »


class Feuille:
    def __init__(self, config: Config):
        if not config.sheet_id:
            raise RuntimeError("Configuration Google Sheets incomplète : définir SHEET_ID.")
        infos = config.infos_compte_service()
        if infos:
            client = gspread.service_account_from_dict(infos)
        else:
            # Sans clé JSON : identité par défaut de l'environnement (ex. compte de
            # service attaché au job Cloud Run). Le Sheet doit être partagé en édition
            # avec ce compte.
            try:
                identifiants, _ = google.auth.default(
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive",
                    ]
                )
            except erreurs_google_auth.DefaultCredentialsError as exc:
                raise RuntimeError(
                    "Aucun accès Google : définir GOOGLE_SERVICE_ACCOUNT_JSON ou "
                    "GOOGLE_SERVICE_ACCOUNT_FILE, ou exécuter dans un environnement "
                    "doté d'une identité par défaut (job Cloud Run)."
                ) from exc
            client = gspread.authorize(identifiants)
        self.classeur = client.open_by_key(config.sheet_id)
        self._nb_lignes_precedentes = 0

    def assurer_structure(self) -> None:
        """Crée les onglets et les en-têtes manquants (ré-exécutable sans danger)."""
        attendus = (
            (ONGLET_SUBVENTIONS, COLONNES),
            (ONGLET_JOURNAL, COLONNES_JOURNAL),
            (ONGLET_ARCHIVES, COLONNES_ARCHIVES),
        )
        for titre, colonnes in attendus:
            try:
                onglet = self.classeur.worksheet(titre)
            except gspread.WorksheetNotFound:
                onglet = self.classeur.add_worksheet(titre, rows=200, cols=len(colonnes) + 2)
                logger.info("Onglet créé : %s", titre)
            if not onglet.row_values(1):
                onglet.update(values=[colonnes], range_name="A1")

    def lire_subventions(self) -> list[LigneSubvention]:
        onglet = self.classeur.worksheet(ONGLET_SUBVENTIONS)
        valeurs = onglet.get_all_values()
        self._nb_lignes_precedentes = max(len(valeurs) - 1, 0)
        return [
            LigneSubvention.depuis_liste(rangee)
            for rangee in valeurs[1:]
            if any(cellule.strip() for cellule in rangee)
        ]

    def ecrire_subventions(self, lignes: list[LigneSubvention]) -> None:
        """Réécrit le tableau en un seul lot, puis efface les lignes devenues orphelines."""
        onglet = self.classeur.worksheet(ONGLET_SUBVENTIONS)
        donnees = [ligne.en_liste() for ligne in lignes]
        if donnees:
            onglet.update(
                values=donnees,
                range_name=f"A2:{_DERNIERE_COLONNE}{len(donnees) + 1}",
                value_input_option="RAW",
            )
        if self._nb_lignes_precedentes > len(donnees):
            onglet.batch_clear(
                [f"A{len(donnees) + 2}:{_DERNIERE_COLONNE}{self._nb_lignes_precedentes + 1}"]
            )

    def archiver(self, lignes: list[LigneSubvention], date_archivage: str) -> None:
        if not lignes:
            return
        onglet = self.classeur.worksheet(ONGLET_ARCHIVES)
        onglet.append_rows(
            [ligne.en_liste() + [date_archivage] for ligne in lignes],
            value_input_option="RAW",
        )
        logger.info("%d ligne(s) expirée(s) archivée(s)", len(lignes))

    def ajouter_journal(self, valeurs: list[str]) -> None:
        onglet = self.classeur.worksheet(ONGLET_JOURNAL)
        onglet.append_row(valeurs, value_input_option="RAW")
