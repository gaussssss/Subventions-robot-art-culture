"""Tests unitaires : normalisation, déduplication et cycle de vie."""

from datetime import date

from veille.dedoublonnage import fusionner, separer_archives, trier
from veille.models import (
    LigneSubvention,
    ProgrammeExtrait,
    calculer_id_unique,
    normaliser_date,
)

AUJOURDHUI = date(2026, 7, 14)


# ── Normalisation des dates ──────────────────────────────────────────────────

def test_date_iso():
    assert normaliser_date("2026-09-15") == "2026-09-15"


def test_date_francaise():
    assert normaliser_date("15 mars 2026") == "2026-03-15"
    assert normaliser_date("1er avril 2026") == "2026-04-01"
    assert normaliser_date("31 décembre 2026") == "2026-12-31"


def test_date_continu():
    assert normaliser_date("Dépôt en continu") == "continu"
    assert normaliser_date("en tout temps") == "continu"


def test_date_inexploitable():
    assert normaliser_date("printemps 2026 (à confirmer)") is None
    assert normaliser_date(None) is None


# ── Clé de déduplication ─────────────────────────────────────────────────────

def test_id_unique_insensible_casse_et_accents():
    assert calculer_id_unique("CALQ", "Soutien à la programmation") == calculer_id_unique(
        " calq ", "soutien a la  programmation"
    )


def test_id_unique_distingue_les_volets_homonymes_par_chemin_url():
    # Même nom de programme, pages différentes → lignes distinctes (volets CALQ).
    a = calculer_id_unique("CALQ", "Partenariat territorial", "https://calq.gouv.qc.ca/aides/volet-1?regions=58")
    b = calculer_id_unique("CALQ", "Partenariat territorial", "https://calq.gouv.qc.ca/aides/volet-2?regions=58")
    assert a != b
    # Les paramètres de requête (cHash, filtres) ne changent pas l'identité.
    assert a == calculer_id_unique(
        "CALQ", "Partenariat territorial", "https://www.calq.gouv.qc.ca/aides/volet-1?cHash=abc"
    )


# ── Validation Pydantic ──────────────────────────────────────────────────────

def _programme(**surcharges) -> ProgrammeExtrait:
    base = {
        "nom_programme": "Programme test",
        "organisme": "CALQ",
        "url": "https://www.calq.gouv.qc.ca/programme",
        "date_limite": "2026-09-15",
    }
    base.update(surcharges)
    return ProgrammeExtrait.model_validate(base, context={"domaines": ["calq.gouv.qc.ca"]})


def test_validation_domaines():
    import pytest

    with pytest.raises(Exception):
        _programme(url="https://autre-site.com/programme")


def test_validation_valeurs_par_defaut():
    p = _programme(admissibilite_obnl=None, type="inconnu")
    assert p.admissibilite_obnl == "À vérifier"
    assert p.type == "Autre"


# ── Fusion et cycle de vie ───────────────────────────────────────────────────

def test_fusion_nouveau_programme():
    fusion = fusionner([], [_programme()], AUJOURDHUI)
    assert len(fusion.nouveautes) == 1
    ligne = fusion.nouveautes[0]
    assert ligne.statut == "Nouveau"
    assert ligne.date_detection == "2026-07-14"


def test_fusion_nouveau_de_la_veille_devient_actif():
    ligne = LigneSubvention(
        nom_programme="P", organisme="O", statut="Nouveau",
        date_detection="2026-07-13", date_limite="2026-09-01", id_unique="abc",
    )
    fusion = fusionner([ligne], [], AUJOURDHUI)
    assert fusion.lignes[0].statut == "Actif"


def test_fusion_expiration():
    ligne = LigneSubvention(
        nom_programme="P", organisme="O", statut="Actif",
        date_detection="2026-06-01", date_limite="2026-07-01", id_unique="abc",
    )
    fusion = fusionner([ligne], [], AUJOURDHUI)
    assert fusion.lignes[0].statut == "Expiré"
    assert fusion.nb_expires == 1


def test_fusion_maj_date_limite_et_pas_ecrasement_par_vide():
    existante = LigneSubvention(
        nom_programme="Programme test", organisme="CALQ", statut="Actif",
        montant="jusqu'à 25 000 $", date_detection="2026-06-01",
        date_limite="2026-08-01",
        id_unique=calculer_id_unique(
            "CALQ", "Programme test", "https://www.calq.gouv.qc.ca/programme"
        ),
    )
    prog = _programme(date_limite="2026-10-01", montant=None)
    fusion = fusionner([existante], [prog], AUJOURDHUI)
    ligne = fusion.lignes[0]
    assert ligne.date_limite == "2026-10-01"
    assert "date limite modifiée" in ligne.notes_agent
    assert ligne.montant == "jusqu'à 25 000 $"  # jamais écrasé par null
    assert ligne.derniere_verification == "2026-07-14"
    assert fusion.nouveautes == []


def test_archives_apres_90_jours():
    vieille = LigneSubvention(
        nom_programme="V", organisme="O", statut="Expiré",
        date_limite="2026-01-01", id_unique="a",
    )
    recente = LigneSubvention(
        nom_programme="R", organisme="O", statut="Expiré",
        date_limite="2026-07-01", id_unique="b",
    )
    garder, archiver = separer_archives([vieille, recente], AUJOURDHUI, 90)
    assert [l.nom_programme for l in archiver] == ["V"]
    assert [l.nom_programme for l in garder] == ["R"]


def test_tri():
    lignes = [
        LigneSubvention(nom_programme="c", statut="Actif", date_limite="continu"),
        LigneSubvention(nom_programme="b", statut="Actif", date_limite="2026-08-01"),
        LigneSubvention(nom_programme="a", statut="Expiré", date_limite="2026-07-01"),
        LigneSubvention(nom_programme="n", statut="Nouveau", date_limite="2026-12-01"),
    ]
    trier(lignes)
    assert [l.nom_programme for l in lignes] == ["n", "b", "c", "a"]


# ── Moteur de scraping ───────────────────────────────────────────────────────

HTML_EXEMPLE = """
<html><body>
<article class="appel">
  <h2><a href="/programmes/creation">Aide à la création</a></h2>
  <span class="date">Date limite : 15 septembre 2026</span>
  <span class="montant">jusqu'à 20 000 $</span>
  <p>Soutien aux projets de création artistique.</p>
</article>
<article class="appel">
  <h2><a href="/programmes/vieux">Ancien appel (archivé)</a></h2>
  <span class="date">1er juin 2025</span>
  <p>Terminé.</p>
</article>
<article class="appel"><p>Bloc sans titre, ignoré.</p></article>
</body></html>
"""

REGLES_EXEMPLE = {
    "bloc": "article.appel",
    "champs": {
        "nom_programme": "h2",
        "url": {"selecteur": "h2 a"},
        "date_limite": {"selecteur": ".date", "regex": r"\d{1,2}(?:er)?\s+\w+\s+\d{4}"},
        "montant": ".montant",
        "type": {"valeur": "Projet"},
        "notes_agent": "p",
    },
    "exclure_si": ["(?i)archiv"],
}


def test_extraire_page():
    from veille.extracteur import extraire_page

    elements = extraire_page(HTML_EXEMPLE, REGLES_EXEMPLE, "https://exemple.org/appels")
    assert len(elements) == 1  # l'archivé et le bloc sans titre sont écartés
    element = elements[0]
    assert element["nom_programme"] == "Aide à la création"
    assert element["url"] == "https://exemple.org/programmes/creation"  # URL absolue
    assert element["date_limite"] == "15 septembre 2026"
    assert element["montant"] == "jusqu'à 20 000 $"
    assert element["type"] == "Projet"


def test_extraire_page_sans_bloc_ni_url():
    from veille.extracteur import extraire_page

    html = "<html><body><h1>Programme unique</h1><p>Détails.</p></body></html>"
    regles = {"champs": {"nom_programme": "h1", "notes_agent": "p"}}
    elements = extraire_page(html, regles, "https://exemple.org/programme")
    assert elements == [
        {
            "nom_programme": "Programme unique",
            "notes_agent": "Détails.",
            "url": "https://exemple.org/programme",  # repli : l'URL de la page
        }
    ]


def test_extraction_puis_validation_pydantic():
    from veille.extracteur import extraire_page

    element = extraire_page(HTML_EXEMPLE, REGLES_EXEMPLE, "https://exemple.org/appels")[0]
    element["organisme"] = "Organisme test"
    prog = ProgrammeExtrait.model_validate(element, context={"domaines": ["exemple.org"]})
    assert prog.date_limite == "2026-09-15"  # normalisation de la date française
    assert prog.admissibilite_obnl == "À vérifier"
