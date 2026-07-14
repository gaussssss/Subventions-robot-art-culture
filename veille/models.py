"""Modèles de données : validation Pydantic, normalisation et lignes du Sheet."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from dateutil import parser as dateutil_parser
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

# Colonnes de l'onglet « Subventions » (section 3.1 des spécifications).
COLONNES = [
    "nom_programme", "organisme", "palier", "discipline", "type", "montant",
    "date_limite", "admissibilite_obnl", "url", "statut", "date_detection",
    "derniere_verification", "notes_agent", "id_unique",
]

COLONNES_JOURNAL = [
    "date", "sources_visitées", "sources_en_erreur", "nouveautés_détectées",
    "programmes_expirés", "coût_api_estimé", "durée_exécution", "alertes",
]

COLONNES_ARCHIVES = COLONNES + ["date_archivage"]

PALIERS = ("Municipal", "Régional", "Provincial", "Fédéral", "Privé")
TYPES = ("Fonctionnement", "Projet", "Immobilisation", "Tournée", "Autre")

STATUT_NOUVEAU = "Nouveau"
STATUT_ACTIF = "Actif"
STATUT_EXPIRE = "Expiré"
ORDRE_STATUTS = {STATUT_NOUVEAU: 0, STATUT_ACTIF: 1, STATUT_EXPIRE: 2}

ADMISSIBLE_A_VERIFIER = "À vérifier"

# Préfixes de mois français (sans accents) pour le parsing tolérant des dates.
_PREFIXES_MOIS = (
    ("janv", 1), ("fev", 2), ("mars", 3), ("avr", 4), ("mai", 5),
    ("juil", 7), ("juin", 6), ("aou", 8), ("sept", 9), ("oct", 10),
    ("nov", 11), ("dec", 12),
)


def _sans_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)
    )


def normaliser_texte(texte: str) -> str:
    return re.sub(r"\s+", " ", _sans_accents(texte).lower()).strip()


def calculer_id_unique(organisme: str, nom_programme: str, url: str = "") -> str:
    """Clé de déduplication : hachage de organisme + nom_programme + chemin de l'URL.

    Le chemin (sans paramètres de requête, qui varient d'une visite à l'autre)
    distingue les volets homonymes d'un même programme — ex. les quatre volets
    « Arts et lettres de la Mauricie - Partenariat territorial » du CALQ, qui
    partagent le même nom mais pas la même page.
    """
    chemin = ""
    if url:
        analysee = urlparse(url)
        chemin = (analysee.netloc.lower().removeprefix("www.") + analysee.path).rstrip("/")
    base = f"{normaliser_texte(organisme)}|{normaliser_texte(nom_programme)}|{chemin.lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def normaliser_date(valeur: object) -> str | None:
    """Parsing tolérant → « AAAA-MM-JJ », « continu » ou None si inexploitable."""
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if not texte or texte.lower() in {"null", "none", "n/a", "-", "?"}:
        return None
    minuscule = normaliser_texte(texte)
    if "continu" in minuscule or "tout temps" in minuscule:
        return "continu"

    # Format ISO (éventuellement suivi d'une heure).
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", texte)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None

    # Format textuel français : « 15 mars 2026 », « 1er avril 2026 ».
    m = re.match(r"^(\d{1,2})(?:er|e)?\s+([a-z.]+)\s+(\d{4})$", minuscule)
    if m:
        mot_mois = m.group(2).rstrip(".")
        for prefixe, numero in _PREFIXES_MOIS:
            if mot_mois.startswith(prefixe):
                try:
                    return date(int(m.group(3)), numero, int(m.group(1))).isoformat()
                except ValueError:
                    return None

    # Dernier recours : dateutil (formats numériques, anglais…), jour en premier.
    try:
        resultat = dateutil_parser.parse(texte, dayfirst=True, fuzzy=False).date()
    except (ValueError, OverflowError):
        return None
    if not 2000 <= resultat.year <= 2100:
        return None
    return resultat.isoformat()


def extraire_domaine(url: str) -> str:
    hote = urlparse(url).netloc.lower()
    return hote.removeprefix("www.")


class ProgrammeExtrait(BaseModel):
    """Programme retourné par l'agent de collecte, avant enrichissement (statut, dates)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nom_programme: str
    organisme: str
    palier: str | None = None
    discipline: str | None = None
    type: str = "Autre"
    montant: str | None = None
    date_limite: str | None = None
    admissibilite_obnl: str = ADMISSIBLE_A_VERIFIER
    url: str
    notes_agent: str | None = None

    @field_validator("nom_programme", "organisme")
    @classmethod
    def _obligatoire(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("champ obligatoire vide")
        return v.strip()

    @field_validator("palier", mode="before")
    @classmethod
    def _normaliser_palier(cls, v: object) -> str | None:
        if v is None:
            return None
        cle = normaliser_texte(str(v))
        for palier in PALIERS:
            if normaliser_texte(palier) == cle:
                return palier
        return None  # rempli en aval avec le palier de la source

    @field_validator("type", mode="before")
    @classmethod
    def _normaliser_type(cls, v: object) -> str:
        if v is None:
            return "Autre"
        cle = normaliser_texte(str(v))
        for type_ in TYPES:
            if normaliser_texte(type_) == cle:
                return type_
        return "Autre"

    @field_validator("admissibilite_obnl", mode="before")
    @classmethod
    def _normaliser_admissibilite(cls, v: object) -> str:
        if v is None:
            return ADMISSIBLE_A_VERIFIER
        cle = normaliser_texte(str(v))
        if cle.startswith("oui"):
            return "Oui"
        if cle.startswith("non"):
            return "Non"
        return ADMISSIBLE_A_VERIFIER

    @field_validator("date_limite", mode="before")
    @classmethod
    def _normaliser_date_limite(cls, v: object) -> str | None:
        return normaliser_date(v)

    @field_validator("url")
    @classmethod
    def _verifier_url(cls, v: str, info: ValidationInfo) -> str:
        # Garde-fou anti-hallucination : URL valide, sur le domaine de la source.
        analysee = urlparse(v)
        if analysee.scheme not in ("http", "https") or not analysee.netloc:
            raise ValueError(f"URL invalide : {v!r}")
        domaines = (info.context or {}).get("domaines") or []
        if domaines:
            hote = analysee.netloc.lower().removeprefix("www.")
            if not any(hote == d or hote.endswith("." + d) for d in domaines):
                raise ValueError(f"URL hors du domaine de la source : {v}")
        return v


@dataclass
class LigneSubvention:
    """Une ligne de l'onglet « Subventions » (14 colonnes, tout en texte)."""

    nom_programme: str = ""
    organisme: str = ""
    palier: str = ""
    discipline: str = ""
    type: str = ""
    montant: str = ""
    date_limite: str = ""
    admissibilite_obnl: str = ""
    url: str = ""
    statut: str = ""
    date_detection: str = ""
    derniere_verification: str = ""
    notes_agent: str = ""
    id_unique: str = ""

    @classmethod
    def depuis_liste(cls, valeurs: list[str]) -> "LigneSubvention":
        ajustees = [str(v).strip() for v in valeurs[: len(COLONNES)]]
        ajustees += [""] * (len(COLONNES) - len(ajustees))
        return cls(*ajustees)

    def en_liste(self) -> list[str]:
        return [getattr(self, colonne) for colonne in COLONNES]

    @classmethod
    def depuis_programme(
        cls, programme: ProgrammeExtrait, id_unique: str, iso_jour: str
    ) -> "LigneSubvention":
        return cls(
            nom_programme=programme.nom_programme,
            organisme=programme.organisme,
            palier=programme.palier or "",
            discipline=programme.discipline or "",
            type=programme.type,
            montant=programme.montant or "",
            date_limite=programme.date_limite or "",
            admissibilite_obnl=programme.admissibilite_obnl,
            url=programme.url,
            statut=STATUT_NOUVEAU,
            date_detection=iso_jour,
            derniere_verification=iso_jour,
            notes_agent=programme.notes_agent or "",
            id_unique=id_unique,
        )
