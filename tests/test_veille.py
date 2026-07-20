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


def test_extraire_page_titre_depuis_slug():
    from veille.extracteur import extraire_page

    # Repli sur le plan de site (sitemap XML) quand la page-liste est en JavaScript :
    # le nom lisible est reconstruit à partir de l'identifiant d'URL.
    sitemap = (
        "<urlset><url><loc>https://arts.org/aides/programmes/sejour-artiste-2026</loc></url>"
        "<url><loc>https://arts.org/aides/programmes/</loc></url></urlset>"
    )
    regles = {
        "bloc": "url",
        "champs": {
            "nom_programme": {
                "selecteur": "loc",
                "regex": r"programmes/([a-z0-9-]+)",
                "titre_depuis_slug": True,
            },
            "url": {"selecteur": "loc"},
        },
    }
    elements = extraire_page(sitemap, regles, "https://arts.org/sitemap.xml")
    assert len(elements) == 1  # l'URL sans slug (la racine) n'a pas de nom
    assert elements[0]["nom_programme"] == "Sejour artiste 2026"


def test_extraction_puis_validation_pydantic():
    from veille.extracteur import extraire_page

    element = extraire_page(HTML_EXEMPLE, REGLES_EXEMPLE, "https://exemple.org/appels")[0]
    element["organisme"] = "Organisme test"
    prog = ProgrammeExtrait.model_validate(element, context={"domaines": ["exemple.org"]})
    assert prog.date_limite == "2026-09-15"  # normalisation de la date française
    assert prog.admissibilite_obnl == "À vérifier"


def _config_appscript():
    from veille.config import Config

    return Config(
        jours_retention_expires=90, delai_entre_requetes_s=1.0, sheet_id=None,
        compte_service_brut=None, compte_service_fichier=None,
        appscript_url="https://script.google.com/macros/s/XXX/exec",
        appscript_jeton="secret-test",
    )


def test_feuille_appscript_payloads_et_lecture(monkeypatch):
    """Le client envoie {jeton, action, ...} et relit les lignes du Sheet."""
    from veille import feuille_appscript
    from veille.models import LigneSubvention

    appels = []

    class _Reponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            action = appels[-1]["json"]["action"]
            if action == "lire":
                ligne = LigneSubvention(nom_programme="Aide", organisme="Org").en_liste()
                return {"ok": True, "lignes": [ligne, [""] * 14]}  # la ligne vide est ignorée
            return {"ok": True}

    monkeypatch.setattr(
        feuille_appscript.requests, "post",
        lambda url, **kw: appels.append({"url": url, **kw}) or _Reponse(),
    )

    feuille = feuille_appscript.FeuilleAppScript(_config_appscript())
    feuille.assurer_structure()
    lignes = feuille.lire_subventions()
    feuille.ecrire_subventions(lignes)
    feuille.ajouter_journal(["2026-07-15", "71"])

    actions = [a["json"]["action"] for a in appels]
    assert actions == ["structure", "lire", "ecrire", "journal"]
    assert all(a["json"]["jeton"] == "secret-test" for a in appels)
    assert len(lignes) == 1 and lignes[0].nom_programme == "Aide"
    assert appels[2]["json"]["lignes"] == [lignes[0].en_liste()]  # aller-retour intact


def test_feuille_appscript_erreur_remontee(monkeypatch):
    """Une réponse {ok: false} de la passerelle devient une exception claire."""
    import pytest

    from veille import feuille_appscript

    class _Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False, "erreur": "jeton invalide"}

    monkeypatch.setattr(feuille_appscript.requests, "post", lambda url, **kw: _Reponse())
    feuille = feuille_appscript.FeuilleAppScript(_config_appscript())
    with pytest.raises(feuille_appscript.ErreurAppScript, match="jeton invalide"):
        feuille.assurer_structure()


def test_ouvrir_feuille_choisit_la_passerelle():
    from veille.config import ouvrir_feuille
    from veille.feuille_appscript import FeuilleAppScript

    assert isinstance(ouvrir_feuille(_config_appscript()), FeuilleAppScript)


# ── Catégorisation pour le classeur manuel ───────────────────────────────────

def _source(**surcharges):
    from veille.extracteur import Source

    base = {"id": "test", "nom": "Source test", "palier": "Provincial"}
    base.update(surcharges)
    return Source(**base)


def test_categorie_héritée_de_la_source():
    from veille.categorisation import categoriser

    source = _source(categorie="Tourisme")
    assert categoriser(_programme(), source) == "Tourisme"


def test_categorie_mots_cles_et_repli():
    from veille.categorisation import categoriser

    source = _source(categorie="À classer", categorie_mots_cles=True)
    assert categoriser(_programme(nom_programme="Aide au patrimoine bâti"), source) == "Patrimoine"
    assert categoriser(_programme(nom_programme="Soutien aux festivals"), source) == "Grands programmes"
    assert categoriser(_programme(nom_programme="Fonds général XYZ"), source) == "À classer"


def test_categorie_regle_transversale_autochtone():
    from veille.categorisation import categoriser

    # Prime même sur une source mono-sujet sans mots-clés.
    source = _source(categorie="Grands programmes")
    p = _programme(nom_programme="Soutien aux artistes autochtones")
    assert categoriser(p, source) == "Autochtones"


# ── Fusion à trois voies avec le classeur manuel ─────────────────────────────

def _onglet(gid, nom, valeurs):
    return {"gid": gid, "nom": nom, "valeurs": valeurs}


def _candidat(programme, source):
    from veille.categorisation import categoriser

    idu = calculer_id_unique(programme.organisme, programme.nom_programme, programme.url)
    return (idu, programme, categoriser(programme, source))


def test_classeur_nouvelle_ligne_dans_le_bon_onglet():
    from veille.classeur import PREFIXE_CLE, planifier

    etat = {"onglets": {}, "lignes": {}}
    onglets = [_onglet(11, "Tourimse", []), _onglet(22, "À classer", [])]
    idu, p, cat = _candidat(_programme(), _source(categorie="Tourisme"))

    plan = planifier(etat, onglets, [(idu, p, cat)])

    assert plan.nb_ajouts == 1 and list(plan.ajouts) == [11]
    rangee = plan.ajouts[11].lignes[0]
    assert rangee[0] == "Programme test"
    assert rangee[-1] == PREFIXE_CLE + idu
    assert (rangee[3], rangee[4], rangee[5]) == ("15", "Septembre", "2026")
    # L'état de la ligne n'est enregistré qu'après l'écriture réussie.
    assert etat["lignes"] == {}


def test_classeur_categorie_inconnue_va_dans_a_classer():
    from veille.classeur import planifier

    etat = {"onglets": {}, "lignes": {}}
    onglets = [_onglet(22, "À classer", [])]
    idu, p, cat = _candidat(_programme(), _source(categorie="Tourisme"))  # pas d'onglet Tourimse

    plan = planifier(etat, onglets, [(idu, p, cat)])
    assert list(plan.ajouts) == [22]


def test_classeur_modif_humaine_preservee_et_maj_machine():
    from veille.classeur import PREFIXE_CLE, ligne_classeur, planifier

    p = _programme()
    idu, _, cat = _candidat(p, _source(categorie="Tourisme"))
    base = ligne_classeur(p)

    # Dans le classeur : l'humain a réécrit le montant (col 8) ; le robot voit
    # une nouvelle date limite dans la collecte du jour.
    ligne_sheet = list(base)
    ligne_sheet[7] = "10 000 $ (confirmé par courriel)"
    ligne_sheet += [""] * (35 - len(ligne_sheet))
    ligne_sheet[34] = PREFIXE_CLE + idu

    etat = {"onglets": {"Tourisme": 11},
            "lignes": {idu: {"gid": 11, "valeurs": base, "categorie": cat, "supprimee": False}}}
    onglets = [_onglet(11, "Renommé par l'humain", [ligne_sheet])]

    p2 = _programme(date_limite="2026-11-30", montant="5 000 $")
    plan = planifier(etat, onglets, [(idu, p2, cat)])

    # Le montant humain n'est PAS écrasé ; les colonnes de date sont mises à jour.
    valeurs_ecrites = {c["colonne"]: c["valeur"] for c in plan.majs[11].cellules}
    assert 8 not in valeurs_ecrites
    assert valeurs_ecrites[4] == "30" and valeurs_ecrites[5] == "Novembre"
    # La base différée retient la valeur humaine.
    assert plan.majs[11].bases[idu][7] == "10 000 $ (confirmé par courriel)"
    assert plan.nb_adoptions >= 1
    # L'onglet renommé reste résolu par son gid mémorisé.
    assert etat["onglets"]["Tourisme"] == 11


def test_classeur_ligne_deplacee_suivie_par_sa_cle():
    from veille.classeur import PREFIXE_CLE, ligne_classeur, planifier

    p = _programme()
    idu, _, cat = _candidat(p, _source(categorie="Tourisme"))
    base = ligne_classeur(p)
    ligne_sheet = list(base) + [""] * (35 - len(base))
    ligne_sheet[34] = PREFIXE_CLE + idu

    etat = {"onglets": {}, "lignes": {idu: {"gid": 11, "valeurs": base,
                                            "categorie": cat, "supprimee": False}}}
    # L'humain a déplacé la ligne de l'onglet 11 vers l'onglet 33.
    onglets = [_onglet(11, "Tourimse", []), _onglet(33, "Grands programmes", [ligne_sheet])]

    plan = planifier(etat, onglets, [(idu, p, cat)])
    assert plan.nb_ajouts == 0 and plan.nb_deplacees == 1
    assert etat["lignes"][idu]["gid"] == 33


def test_classeur_ligne_supprimee_jamais_reajoutee():
    from veille.classeur import planifier

    p = _programme()
    idu, _, cat = _candidat(p, _source(categorie="Tourisme"))
    etat = {"onglets": {}, "lignes": {idu: {"gid": 11, "valeurs": ["x"] * 14,
                                            "categorie": cat, "supprimee": False}}}
    onglets = [_onglet(11, "Tourimse", []), _onglet(22, "À classer", [])]

    plan = planifier(etat, onglets, [(idu, p, cat)])
    assert plan.nb_supprimees == 1 and plan.nb_ajouts == 0
    assert etat["lignes"][idu]["supprimee"] is True

    # Et au passage suivant non plus.
    plan2 = planifier(etat, onglets, [(idu, p, cat)])
    assert plan2.nb_ajouts == 0 and plan2.nb_supprimees == 0


def test_classeur_cle_retrouvee_meme_deplacee_en_colonne():
    """Une insertion de colonne décale la clé : elle doit rester détectée, et
    le décalage des valeurs est traité comme des modifs humaines (adoption)."""
    from veille.classeur import PREFIXE_CLE, ligne_classeur, planifier

    p = _programme()
    idu, _, cat = _candidat(p, _source(categorie="Tourisme"))
    base = ligne_classeur(p)
    ligne_sheet = [""] + list(base) + [""] * 10  # colonne insérée en tête
    ligne_sheet.append(PREFIXE_CLE + idu)        # clé décalée en bout de ligne

    etat = {"onglets": {}, "lignes": {idu: {"gid": 11, "valeurs": base,
                                            "categorie": cat, "supprimee": False}}}
    onglets = [_onglet(11, "Tourimse", [ligne_sheet])]

    plan = planifier(etat, onglets, [(idu, p, cat)])
    # Pas de ré-ajout, pas de suppression : la ligne est bien retrouvée.
    assert plan.nb_ajouts == 0 and plan.nb_supprimees == 0
