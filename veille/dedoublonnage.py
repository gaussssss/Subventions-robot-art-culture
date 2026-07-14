"""Déduplication et cycle de vie des lignes du Sheet (section 4.4 des spécifications)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .models import (
    ORDRE_STATUTS,
    STATUT_ACTIF,
    STATUT_EXPIRE,
    STATUT_NOUVEAU,
    LigneSubvention,
    ProgrammeExtrait,
    calculer_id_unique,
)

# Champs mis à jour lorsqu'un programme connu est revu — jamais écrasés par du vide.
_CHAMPS_MAJ = ("palier", "discipline", "type", "montant", "admissibilite_obnl", "url", "notes_agent")


@dataclass
class Fusion:
    lignes: list[LigneSubvention]
    nouveautes: list[LigneSubvention] = field(default_factory=list)
    nb_expires: int = 0
    nb_maj_dates: int = 0


def _date_iso(valeur: str) -> date | None:
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return None


def fusionner(
    existantes: list[LigneSubvention],
    programmes: list[ProgrammeExtrait],
    aujourdhui: date,
) -> Fusion:
    iso_jour = aujourdhui.isoformat()

    # Lignes ajoutées à la main sans id_unique : on le calcule pour les dédupliquer aussi.
    for ligne in existantes:
        if not ligne.id_unique and ligne.organisme and ligne.nom_programme:
            ligne.id_unique = calculer_id_unique(ligne.organisme, ligne.nom_programme, ligne.url)

    index = {ligne.id_unique: ligne for ligne in existantes if ligne.id_unique}
    fusion = Fusion(lignes=list(existantes))
    vus: set[str] = set()

    for programme in programmes:
        idu = calculer_id_unique(programme.organisme, programme.nom_programme, programme.url)
        if idu in vus:
            continue  # doublon au sein de la même exécution
        vus.add(idu)

        ligne = index.get(idu)
        if ligne is None:
            nouvelle = LigneSubvention.depuis_programme(programme, idu, iso_jour)
            index[idu] = nouvelle
            fusion.lignes.append(nouvelle)
            fusion.nouveautes.append(nouvelle)
            continue

        # Programme connu : mise à jour, sans jamais écraser une valeur par du vide.
        ligne.derniere_verification = iso_jour
        for champ in _CHAMPS_MAJ:
            valeur = getattr(programme, champ)
            if valeur:
                setattr(ligne, champ, valeur)

        ancienne_date = ligne.date_limite
        nouvelle_date = programme.date_limite or ""
        if nouvelle_date and nouvelle_date != ancienne_date:
            ligne.date_limite = nouvelle_date
            note = f"[MAJ {iso_jour}] date limite modifiée : {ancienne_date or '?'} → {nouvelle_date}."
            ligne.notes_agent = f"{ligne.notes_agent} {note}".strip()
            fusion.nb_maj_dates += 1
            # Un programme expiré qui revient avec une échéance future redevient actif
            # (appel récurrent : nouvelle édition du même programme).
            d = _date_iso(nouvelle_date)
            if ligne.statut == STATUT_EXPIRE and (nouvelle_date == "continu" or (d and d >= aujourdhui)):
                ligne.statut = STATUT_ACTIF

    # Cycle de vie.
    for ligne in fusion.lignes:
        d = _date_iso(ligne.date_limite)
        if d is not None and d < aujourdhui:
            if ligne.statut != STATUT_EXPIRE:
                ligne.statut = STATUT_EXPIRE
                fusion.nb_expires += 1
        elif ligne.statut == STATUT_NOUVEAU and ligne.date_detection and ligne.date_detection < iso_jour:
            # Les « Nouveau » de la veille passent à « Actif » à l'exécution suivante.
            ligne.statut = STATUT_ACTIF

    return fusion


def separer_archives(
    lignes: list[LigneSubvention], aujourdhui: date, jours_retention: int
) -> tuple[list[LigneSubvention], list[LigneSubvention]]:
    """Les lignes expirées depuis plus de `jours_retention` jours partent aux Archives."""
    garder: list[LigneSubvention] = []
    archiver: list[LigneSubvention] = []
    for ligne in lignes:
        d = _date_iso(ligne.date_limite)
        if ligne.statut == STATUT_EXPIRE and d and (aujourdhui - d).days > jours_retention:
            archiver.append(ligne)
        else:
            garder.append(ligne)
    return garder, archiver


def trier(lignes: list[LigneSubvention]) -> None:
    """Tri d'affichage : statut (Nouveau d'abord), puis date_limite croissante.

    Au sein d'un statut : dates connues croissantes, puis « continu », puis sans date.
    """

    def cle(ligne: LigneSubvention):
        statut = ORDRE_STATUTS.get(ligne.statut, 3)
        d = _date_iso(ligne.date_limite)
        if d is not None:
            groupe, valeur = 0, d.isoformat()
        elif ligne.date_limite == "continu":
            groupe, valeur = 1, ""
        else:
            groupe, valeur = 2, ""
        return (statut, groupe, valeur, ligne.nom_programme.lower())

    lignes.sort(key=cle)
