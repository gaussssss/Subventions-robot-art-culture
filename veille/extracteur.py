"""Extracteur par scraping pur : requêtes HTTP + règles CSS par source (aucune IA).

Le catalogue des sources et leurs règles vivent dans `sources.json`. Chaque page
d'une source porte ses règles ; en modifier une n'exige aucun changement de code.

Schéma des règles d'une page :

    {
      "url": "https://exemple.org/appels",
      "regles": {
        "bloc": "article.appel",                  // sélecteur CSS : un bloc = un programme
        "champs": {
          "nom_programme": "h2",                  // chaîne = sélecteur, texte extrait
          "url": {"selecteur": "a", "attribut": "href"},   // attribut plutôt que texte
          "date_limite": {"selecteur": ".date", "regex": "\\d{1,2} \\w+ \\d{4}"},
          "montant": ".montant",
          "type": {"valeur": "Projet"},           // valeur fixe, sans extraction
          "notes_agent": "p"
        },
        "exclure_si": ["(?i)archiv", "(?i)terminé"]   // regex sur nom_programme
      },
      "statut_regles": "testées AAAA-MM-JJ"
    }

Notes :
- `champs` accepte une chaîne (raccourci pour {"selecteur": ...}) ou un objet
  {selecteur, attribut, regex, valeur}. `regex` garde le groupe 1 s'il existe,
  sinon la correspondance entière ; aucune correspondance → champ vide.
- Pour le champ `url`, l'attribut par défaut est `href` si la cible est un lien,
  et les URL relatives sont résolues par rapport à la page.
- `bloc` absent → la page entière est un seul bloc (fiche de programme unique).
- Un bloc sans `nom_programme` est ignoré. Sans `url`, l'URL de la page est utilisée.
- `organisme` et `palier` héritent de la source s'ils ne sont pas extraits.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from .models import ProgrammeExtrait, extraire_domaine

logger = logging.getLogger(__name__)

ENTETES = {
    "User-Agent": "Mozilla/5.0 (compatible; VeilleSubventions/2.0; OBNL culturel Mauricie)",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.5",
}
DELAI_ENTRE_REQUETES_S = 1.0
TENTATIVES = 3
DELAI_EXPIRATION_S = 30


@dataclass
class Page:
    url: str
    regles: dict | None = None
    statut_regles: str = ""


@dataclass
class Source:
    id: str
    nom: str
    palier: str
    pages: list[Page] = field(default_factory=list)
    notes: str = ""
    domaines_supplementaires: list[str] = field(default_factory=list)
    actif: bool = True


def charger_sources(chemin: Path) -> list[Source]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    sources = []
    for entree in donnees.get("sources", []):
        pages = [
            Page(
                url=p["url"],
                regles=p.get("regles"),
                statut_regles=p.get("statut_regles", ""),
            )
            for p in entree.get("pages", [])
        ]
        sources.append(
            Source(
                id=entree["id"],
                nom=entree["nom"],
                palier=entree["palier"],
                pages=pages,
                notes=(entree.get("notes") or "").strip(),
                domaines_supplementaires=list(entree.get("domaines_supplementaires") or []),
                actif=bool(entree.get("actif", True)),
            )
        )
    return sources


@dataclass
class ResultatSource:
    source: Source
    programmes: list[ProgrammeExtrait] = field(default_factory=list)
    rejets: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    pages_sans_regles: int = 0
    erreur: str | None = None
    duree_s: float = 0.0


def domaines(source: Source) -> list[str]:
    resultat = {extraire_domaine(p.url) for p in source.pages}
    resultat.update(d.lower().removeprefix("www.") for d in source.domaines_supplementaires)
    return sorted(d for d in resultat if d)


def recuperer(url: str, tentatives: int = TENTATIVES) -> str:
    """Télécharge une page, avec relances et backoff exponentiel (section 6 des specs)."""
    derniere: Exception | None = None
    for tentative in range(tentatives):
        try:
            reponse = requests.get(url, headers=ENTETES, timeout=DELAI_EXPIRATION_S)
            reponse.raise_for_status()
            return reponse.text
        except requests.RequestException as exc:
            derniere = exc
            if tentative < tentatives - 1:
                time.sleep(5 * 2**tentative)
    raise RuntimeError(f"échec après {tentatives} tentatives : {derniere}")


def _normaliser_spec(spec) -> dict:
    if isinstance(spec, str):
        return {"selecteur": spec, "attribut": None, "regex": None, "valeur": None}
    return {
        "selecteur": spec.get("selecteur"),
        "attribut": spec.get("attribut"),
        "regex": spec.get("regex"),
        "valeur": spec.get("valeur"),
    }


def _extraire_champ(bloc, spec: dict, nom_champ: str) -> str | None:
    if spec["valeur"] is not None:
        return str(spec["valeur"])
    cible = bloc.select_one(spec["selecteur"]) if spec["selecteur"] else bloc
    if cible is None:
        return None
    attribut = spec["attribut"]
    if attribut is None and nom_champ == "url" and cible.name == "a":
        attribut = "href"
    brut = (cible.get(attribut) or "") if attribut else cible.get_text(" ", strip=True)
    brut = str(brut)
    if spec["regex"]:
        correspondance = re.search(spec["regex"], brut)
        if not correspondance:
            return None
        brut = correspondance.group(1) if correspondance.groups() else correspondance.group(0)
    brut = re.sub(r"\s+", " ", brut).strip()
    return brut or None


def extraire_page(html: str, regles: dict, url_page: str) -> list[dict]:
    """Applique les règles d'une page et retourne les programmes bruts (dicts)."""
    soupe = BeautifulSoup(html, "lxml")
    blocs = soupe.select(regles["bloc"]) if regles.get("bloc") else [soupe]
    exclusions = [re.compile(motif) for motif in regles.get("exclure_si", [])]

    resultats = []
    for bloc in blocs:
        element: dict = {}
        for nom_champ, spec in (regles.get("champs") or {}).items():
            element[nom_champ] = _extraire_champ(bloc, _normaliser_spec(spec), nom_champ)
        nom = element.get("nom_programme")
        if not nom:
            continue
        if any(motif.search(nom) for motif in exclusions):
            continue
        if element.get("url"):
            element["url"] = urljoin(url_page, element["url"])
        else:
            element["url"] = url_page
        resultats.append(element)
    return resultats


def collecter_source(
    source: Source, jour: date, delai_s: float = DELAI_ENTRE_REQUETES_S
) -> ResultatSource:
    """Scrape toutes les pages d'une source. Une page en échec ne bloque pas les autres."""
    debut = time.monotonic()
    resultat = ResultatSource(source=source)
    contexte = {"domaines": domaines(source), "palier_source": source.palier}

    pages_avec_regles = [p for p in source.pages if p.regles is not None]
    resultat.pages_sans_regles = len(source.pages) - len(pages_avec_regles)
    if resultat.pages_sans_regles:
        logger.debug("[%s] %d page(s) sans règles de scraping", source.id, resultat.pages_sans_regles)

    nb_echecs_reseau = 0
    for indice, page in enumerate(pages_avec_regles):
        if indice:
            time.sleep(delai_s)  # politesse entre deux requêtes au même site
        try:
            html = recuperer(page.url)
        except Exception as exc:
            nb_echecs_reseau += 1
            resultat.avertissements.append(f"{page.url} : {exc}")
            continue

        elements = extraire_page(html, page.regles, page.url)
        if not elements:
            # Signal principal de robustesse : une règle qui ne trouve plus rien
            # indique probablement un changement de mise en page.
            resultat.avertissements.append(
                f"{page.url} : 0 programme extrait (mise en page changée ?)"
            )
        for element in elements:
            if not element.get("organisme"):
                element["organisme"] = source.nom
            if not element.get("palier"):
                element["palier"] = source.palier
            try:
                programme = ProgrammeExtrait.model_validate(element, context=contexte)
            except ValidationError as exc:
                nom = element.get("nom_programme") or "?"
                resultat.rejets.append(f"{nom} : {exc.errors()[0].get('msg', 'entrée invalide')}")
                continue
            if not programme.palier:
                programme.palier = source.palier
            resultat.programmes.append(programme)

    if pages_avec_regles and nb_echecs_reseau == len(pages_avec_regles):
        resultat.erreur = "toutes les pages de la source sont inaccessibles"

    resultat.duree_s = time.monotonic() - debut
    return resultat
