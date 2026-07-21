"""Point d'entrée : scraping → validation → déduplication → Google Sheets.

v2 « scraping pur » : aucune IA, aucun courriel. Les erreurs et alertes sont
consignées dans l'onglet Journal du Sheet et dans les journaux d'exécution.

Usage :
    python -m veille.main                     # exécution complète
    python -m veille.main --console           # résultats en JSON dans la console, sans Sheet
    python -m veille.main --sources id1,id2   # limiter à certaines sources
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime

from . import extracteur
from .config import (
    DOSSIER_SORTIE,
    FICHIER_SOURCES,
    FUSEAU_HORAIRE,
    Config,
    charger_config,
    ouvrir_feuille,
)
from .dedoublonnage import fusionner, separer_archives, trier

logger = logging.getLogger("veille")


def _formater_duree(secondes: float) -> str:
    return f"{int(secondes // 60)}m{int(secondes % 60):02d}s"


def _sauvegarder_json(maintenant: datetime, resultats):
    """Sauvegarde locale systématique — filet de sécurité si Google Sheets échoue."""
    DOSSIER_SORTIE.mkdir(exist_ok=True)
    chemin = DOSSIER_SORTIE / f"resultats-{maintenant.date().isoformat()}.json"
    contenu = {
        "date": maintenant.isoformat(),
        "sources": [
            {
                "id": r.source.id,
                "nom": r.source.nom,
                "erreur": r.erreur,
                "avertissements": r.avertissements,
                "rejets": r.rejets,
                "nb_programmes": len(r.programmes),
                "duree_s": round(r.duree_s, 1),
                "programmes": [p.model_dump() for p in r.programmes],
            }
            for r in resultats
        ],
    }
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Résultats sauvegardés : %s", chemin)
    return chemin


def _executer(args, config: Config) -> int:
    maintenant = datetime.now(FUSEAU_HORAIRE)
    aujourdhui = maintenant.date()
    debut = time.monotonic()

    sources = [s for s in extracteur.charger_sources(FICHIER_SOURCES) if s.actif]
    if args.sources:
        demandes = {s.strip() for s in args.sources.split(",") if s.strip()}
        inconnues = demandes - {s.id for s in sources}
        if inconnues:
            logger.error("Sources inconnues ou inactives : %s", ", ".join(sorted(inconnues)))
            return 1
        sources = [s for s in sources if s.id in demandes]
    if not sources:
        logger.error("Aucune source active dans %s", FICHIER_SOURCES)
        return 1

    # ── 1. Scraping (source par source, erreurs isolées) ─────────────────────
    resultats = []
    for source in sources:
        logger.info("Scraping : %s (%d page(s))", source.nom, len(source.pages))
        resultat = extracteur.collecter_source(source, aujourdhui, config.delai_entre_requetes_s)
        if resultat.erreur:
            logger.warning("[%s] en erreur : %s", source.id, resultat.erreur)
        else:
            logger.info("[%s] %d programme(s), %d rejet(s)", source.id,
                        len(resultat.programmes), len(resultat.rejets))
        for avertissement in resultat.avertissements:
            logger.warning("[%s] %s", source.id, avertissement)
        for rejet in resultat.rejets:
            logger.warning("[%s] entrée rejetée — %s", source.id, rejet)
        resultats.append(resultat)

    programmes = [p for r in resultats for p in r.programmes]
    erreurs_sources = [(r.source.nom, r.erreur) for r in resultats if r.erreur]
    avertissements = [f"{r.source.id} — {a}" for r in resultats for a in r.avertissements]
    sans_regles = [r.source.id for r in resultats if r.pages_sans_regles]
    if sans_regles:
        # Mention compacte : les sources cataloguées dont les règles restent à écrire.
        avertissements.append(f"règles à écrire : {', '.join(sans_regles)}")

    chemin_resultats = _sauvegarder_json(maintenant, resultats)

    if args.console:
        print(json.dumps([p.model_dump() for p in programmes], ensure_ascii=False, indent=2))
        logger.info("Mode console : %d programme(s) extraits de %d source(s)",
                    len(programmes), len(sources))
        return 1 if erreurs_sources and len(erreurs_sources) == len(sources) else 0

    # ── 2-4. Déduplication, cycle de vie, écriture du Sheet ──────────────────
    try:
        feuille = ouvrir_feuille(config)
        feuille.assurer_structure()
        existantes = feuille.lire_subventions()
        fusion = fusionner(existantes, programmes, aujourdhui)
        a_garder, a_archiver = separer_archives(
            fusion.lignes, aujourdhui, config.jours_retention_expires
        )
        trier(a_garder)
        feuille.archiver(a_archiver, aujourdhui.isoformat())
        feuille.ecrire_subventions(a_garder)
        logger.info(
            "Feuille mise à jour : %d ligne(s), %d nouveauté(s), %d expiration(s), %d archivée(s)",
            len(a_garder), len(fusion.nouveautes), fusion.nb_expires, len(a_archiver),
        )
    except Exception:
        logger.exception("Échec de la mise à jour Google Sheets")
        # La collecte du jour est déjà sauvegardée : on rappelle seulement où la
        # retrouver (ne PAS la déverser dans la console, elle noierait l'erreur).
        logger.error("Collecte du jour conservée dans : %s", chemin_resultats)
        return 1

    # ── 5. Distribution vers le classeur manuel (si configuré) ──────────────
    # Aucune collecte supplémentaire : on redistribue les mêmes résultats.
    if config.classeur_appscript_url:
        from . import classeur as module_classeur

        try:
            resume_classeur = module_classeur.synchroniser(config, resultats)
            logger.info("Classeur : %s", resume_classeur)
            avertissements.append(f"classeur : {resume_classeur}")
        except Exception as exc:
            logger.exception("Échec de la distribution vers le classeur (la veille continue)")
            avertissements.append(f"classeur en échec : {exc}")

    # ── Journal ───────────────────────────────────────────────────────────────
    duree = time.monotonic() - debut
    entree_journal = [
        aujourdhui.isoformat(),
        str(len(sources) - len(erreurs_sources)),
        "; ".join(f"{nom} ({erreur})" for nom, erreur in erreurs_sources),
        str(len(fusion.nouveautes)),
        str(fusion.nb_expires),
        "0 $ (scraping)",
        _formater_duree(duree),
        "; ".join(avertissements),
    ]
    try:
        feuille.ajouter_journal(entree_journal)
    except Exception:
        logger.exception("Impossible d'écrire dans le Journal (la veille continue)")

    logger.info(
        "Terminé en %s — %d nouveauté(s), %d source(s) en erreur, %d avertissement(s)",
        _formater_duree(duree), len(fusion.nouveautes), len(erreurs_sources),
        len(avertissements),
    )

    # Une source en panne n'est pas un échec global ; toutes en panne, oui.
    if erreurs_sources and len(erreurs_sources) == len(sources):
        logger.error("Toutes les sources sont en erreur — échec global")
        return 1
    return 0


def principal(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Veille quotidienne des subventions art et culture (scraping pur)"
    )
    analyseur.add_argument(
        "--console", action="store_true",
        help="scraping seulement : résultats en JSON sur la sortie standard, sans Google Sheets",
    )
    analyseur.add_argument(
        "--sources", metavar="IDS",
        help="ids de sources à traiter, séparés par des virgules (voir sources.json)",
    )
    args = analyseur.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    config = charger_config()
    try:
        return _executer(args, config)
    except Exception:
        logger.exception("Échec global de la veille")
        return 1


if __name__ == "__main__":
    sys.exit(principal())
