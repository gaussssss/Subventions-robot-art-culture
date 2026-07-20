"""Classement des programmes dans les catégories du classeur manuel.

Arbre de décision, entièrement déterministe (aucune IA) :
  1. règle transversale : un programme dont le nom ou les notes mentionnent les
     communautés autochtones va dans « Autochtones », quelle que soit sa source ;
  2. sources agrégatrices (categorie_mots_cles=true dans sources.json) :
     classement programme par programme par mots-clés, première règle gagnante ;
  3. sinon : le programme hérite de la catégorie de sa source (champ categorie).

Les noms de catégories sont canoniques ; leur correspondance avec les onglets
réels du classeur (fautes de frappe et espaces compris) vit dans classeur.py.
"""

from __future__ import annotations

import re

from .extracteur import Source
from .models import ProgrammeExtrait, normaliser_texte

CATEGORIE_PAR_DEFAUT = "À classer"

CATEGORIES = (
    "Grands programmes", "Régional - Mauricie", "Tourisme", "Patrimoine",
    "Innovation - techno", "Environnement", "Agroalimentaire", "Économie sociale",
    "Travailleurs", "Entrepreneuriat", "Montréal", "International", "Handicap",
    "Arts visuels", "Médiation", "Fondations et autres", "Autochtones",
    "Science et art", "Scolaire, éducatif", "Diversité", CATEGORIE_PAR_DEFAUT,
)

# Règle transversale, appliquée à toutes les sources (décision du 2026-07-20 :
# sans elle, l'onglet Autochtones ne recevrait jamais rien).
_REGLE_AUTOCHTONE = re.compile(r"autochtone|premiere?s? nations?|\binuit|\bmetis\b")

# Règles pour les sources agrégatrices — motifs appliqués au texte normalisé
# (minuscules, sans accents). L'ordre compte : première correspondance gagnante,
# du plus spécifique au plus générique.
_REGLES_MOTS_CLES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(motif), categorie)
    for motif, categorie in [
        (r"mediation", "Médiation"),
        (r"patrimoine|commemorat|religieux", "Patrimoine"),
        (r"touris", "Tourisme"),
        (r"agroalimentaire|agricole|agricult|bioalimentaire|terroir", "Agroalimentaire"),
        (r"environnement|climat|ecologi|developpement durable|biodiversit", "Environnement"),
        (r"scolaire|ecole|education|etudiant", "Scolaire, éducatif"),
        (r"handicap|capacitaire|\bsourd|aveugle|accessibilit", "Handicap"),
        (r"numerique|technologi|innovation|intelligence artificielle|\bia\b", "Innovation - techno"),
        (r"economie sociale|solidaire", "Économie sociale"),
        (r"diversite|inclusion|immigrant|interculturel", "Diversité"),
        (r"emploi|salarial|\bstage|main-d.?oeuvre", "Travailleurs"),
        (r"entrepreneur|demarrage|entreprise", "Entrepreneuriat"),
        (r"international|export|etranger", "International"),
        (r"musique|danse|theatre|cinema|litterature|chanson|\bopera|cirque|festival|\bart\b|\barts\b|culture", "Grands programmes"),
    ]
)


def categoriser(programme: ProgrammeExtrait, source: Source) -> str:
    """Retourne la catégorie canonique d'un programme collecté."""
    texte = normaliser_texte(f"{programme.nom_programme} {programme.notes_agent or ''}")
    if _REGLE_AUTOCHTONE.search(texte):
        return "Autochtones"
    if source.categorie_mots_cles:
        for motif, categorie in _REGLES_MOTS_CLES:
            if motif.search(texte):
                return categorie
    return source.categorie or CATEGORIE_PAR_DEFAUT
