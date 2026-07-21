"""Distribution des subventions collectées vers le classeur manuel (2e Google Sheet).

Le classeur est un document vivant, trié et annoté à la main : le robot fusionne
au lieu d'écraser (fusion à trois voies). Il compare trois versions de chaque
ligne — ce qu'il a écrit la dernière fois (la « base », mémorisée dans
etat/classeur-etat.json), ce qui est dans le classeur maintenant, et ce que la
collecte du jour rapporte — puis applique les règles :

  - cellule modifiée à la main depuis le dernier passage → la valeur humaine
    gagne, toujours (elle devient la nouvelle base) ;
  - cellule intacte et nouvelle valeur collectée → mise à jour ;
  - ligne déplacée dans un autre onglet → retrouvée par sa clé, mise à jour sur
    place (le choix humain de catégorie est retenu) ;
  - ligne supprimée à la main → jamais ré-ajoutée (voir --reactiver) ;
  - programme jamais vu → ajouté à la suite de l'onglet de sa catégorie.

Chaque ligne du robot porte une clé « rbt:<id_unique> » dans une colonne
éloignée (AI). La clé est retrouvée en balayant toute la grille : elle survit
aux tris, aux déplacements et aux insertions de colonnes. Les onglets sont
suivis par leur identifiant interne (gid), qui survit aux renommages.

Le robot n'écrit que des VALEURS — jamais de couleur ni de mise en forme :
les codes couleurs manuels restent intacts.

Usage direct :
    python -m veille.classeur --resume            # état local en bref
    python -m veille.classeur --reactiver ID,ID   # ré-autoriser des lignes supprimées
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from .categorisation import CATEGORIE_PAR_DEFAUT, categoriser
from .config import RACINE, Config
from .extracteur import ResultatSource
from .feuille_appscript import ErreurAppScript, appeler_passerelle
from .models import ProgrammeExtrait, calculer_id_unique

logger = logging.getLogger(__name__)

FICHIER_ETAT = RACINE / "etat" / "classeur-etat.json"

PREFIXE_CLE = "rbt:"
NB_COLONNES = 14  # les 14 colonnes du schéma du classeur (A à N)
COLONNE_CLE = 35  # colonne AI : loin à droite de tout contenu manuel observé
TAILLE_LOT = 50   # lignes/cellules par appel ; réduit tout seul si l'envoi est
                  # tronqué par un antivirus/pare-feu (voir _envoyer_adaptatif)

# Catégorie canonique → nom d'onglet du classeur, tel quel (fautes de frappe et
# espaces compris — décision du 2026-07-20 : on prend les onglets comme ils sont).
# Ne sert qu'à la première résolution : ensuite le gid mémorisé fait foi.
ONGLET_PAR_CATEGORIE = {
    "Grands programmes": "Grands programmes",
    "Régional - Mauricie": "Régional - Mauricie ",
    "Tourisme": "Tourimse",
    "Patrimoine": "Patrimoine",
    "Innovation - techno": "Innov - techno",
    "Environnement": "environnemental",
    "Agroalimentaire": "Agroalimentaire",
    "Économie sociale": "Économie sociale",
    "Travailleurs": " Travailleurs",
    "Entrepreneuriat": "Entrepreneuriat",
    "Montréal": "Montréal",
    "International": "International",
    "Handicap": "Handicap, diversité capacitaire",
    "Arts visuels": "Arts visuels",
    "Médiation": "Médiation",
    "Fondations et autres": "Fondations et autres",
    "Autochtones": "Autochtones",
    "Science et art": "Copie de Science et art",
    "Scolaire, éducatif": "Scolaire, éducatif",
    "Diversité": "Diversité",
    CATEGORIE_PAR_DEFAUT: "À classer",
}

MOIS_FR = ("Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
           "Août", "Septembre", "Octobre", "Novembre", "Décembre")

_POUR_QUI = {"Oui": "OBNL", "Non": "Voir critères"}


# ─── Construction d'une ligne au schéma du classeur ──────────────────────────

def _jour_mois_annee(date_limite: str | None) -> tuple[str, str, str]:
    if not date_limite:
        return "", "", ""
    if date_limite == "continu":
        return "", "En continu", ""
    try:
        d = date.fromisoformat(date_limite)
    except ValueError:
        return "", "", ""
    return str(d.day), MOIS_FR[d.month - 1], str(d.year)


def ligne_classeur(programme: ProgrammeExtrait) -> list[str]:
    """Les 14 colonnes du classeur : Subventions, Détail, Projet possible,
    Jour, Mois, Année, Délai de réponse, Montant, Pour qui, Type, Région,
    Détails, Contact, Site. « Projet possible » et « Délai de réponse »
    restent vides : ce sont des colonnes humaines."""
    jour, mois, annee = _jour_mois_annee(programme.date_limite)
    return [
        programme.nom_programme,
        programme.discipline or "",
        "",  # Projet possible — colonne humaine
        jour, mois, annee,
        "",  # Délai de réponse — inconnu du robot
        programme.montant or "",
        _POUR_QUI.get(programme.admissibilite_obnl, "À vérifier"),
        programme.type,
        programme.palier or "",
        (programme.notes_agent or "")[:250],
        programme.organisme,
        programme.url,
    ]


def _rangee_avec_cle(valeurs: list[str], id_unique: str) -> list[str]:
    rangee = list(valeurs) + [""] * (COLONNE_CLE - len(valeurs))
    rangee[COLONNE_CLE - 1] = PREFIXE_CLE + id_unique
    return rangee


# ─── État local (la « base » de la fusion à trois voies) ─────────────────────

def charger_etat() -> dict:
    if FICHIER_ETAT.exists():
        return json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
    return {"onglets": {}, "lignes": {}}


def sauvegarder_etat(etat: dict) -> None:
    FICHIER_ETAT.parent.mkdir(exist_ok=True)
    FICHIER_ETAT.write_text(
        json.dumps(etat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


# ─── Résolution des onglets et localisation des clés ─────────────────────────

def _normaliser_nom(nom: str) -> str:
    """Normalise un nom d'onglet pour la correspondance : ponctuation neutralisée
    (tirets, virgules, « ? » ajoutés à la main…), espaces réduits, casse ignorée.
    Ainsi « Régional - Mauricie ? » et « Régional - Mauricie » se correspondent."""
    sans_ponctuation = re.sub(r"[^\w\s]", " ", nom, flags=re.UNICODE)
    return re.sub(r"\s+", " ", sans_ponctuation).strip().casefold()


def resoudre_onglets(etat: dict, onglets: list[dict]) -> dict[str, int]:
    """Catégorie canonique → gid. Le gid mémorisé prime (survit au renommage) ;
    à défaut, l'onglet est retrouvé par son nom. Catégorie irrésolue → absente
    (l'appelant se rabat sur « À classer »)."""
    gids_presents = {o["gid"] for o in onglets}
    par_nom = {_normaliser_nom(o["nom"]): o["gid"] for o in onglets}
    resolution: dict[str, int] = {}
    for categorie, nom_onglet in ONGLET_PAR_CATEGORIE.items():
        gid = etat.get("onglets", {}).get(categorie)
        if gid in gids_presents:
            resolution[categorie] = gid
        elif (gid := par_nom.get(_normaliser_nom(nom_onglet))) is not None:
            resolution[categorie] = gid
    return resolution


def _localiser_cles(onglets: list[dict]) -> dict[str, tuple[int, int, list]]:
    """id_unique → (gid, numéro de ligne 1-based, valeurs de la ligne).
    Cherche le préfixe de clé dans toute la grille : survit aux tris,
    déplacements entre onglets et insertions de colonnes."""
    localisation: dict[str, tuple[int, int, list]] = {}
    for onglet in onglets:
        for numero, rangee in enumerate(onglet["valeurs"], start=1):
            for cellule in rangee:
                texte = str(cellule).strip()
                if texte.startswith(PREFIXE_CLE):
                    localisation[texte[len(PREFIXE_CLE):]] = (onglet["gid"], numero, rangee)
                    break
    return localisation


# ─── Planification de la fusion ──────────────────────────────────────────────

@dataclass
class Ajouts:
    """Lignes à ajouter à un onglet ; l'état n'est mis à jour qu'après succès."""
    gid: int
    lignes: list[list[str]] = field(default_factory=list)
    entrees: list[tuple[str, dict]] = field(default_factory=list)  # (id, entrée d'état)


@dataclass
class Maj:
    """Cellules à corriger dans un onglet ; idem, état différé."""
    gid: int
    cellules: list[dict] = field(default_factory=list)
    bases: dict[str, list[str]] = field(default_factory=dict)  # id → nouvelle base


@dataclass
class Plan:
    ajouts: dict[int, Ajouts] = field(default_factory=dict)
    majs: dict[int, Maj] = field(default_factory=dict)
    nb_ajouts: int = 0
    nb_cellules: int = 0
    nb_adoptions: int = 0    # cellules modifiées à la main, adoptées comme base
    nb_deplacees: int = 0
    nb_supprimees: int = 0   # nouvellement constatées supprimées
    nb_sans_onglet: int = 0

    def resume(self) -> str:
        return (f"{self.nb_ajouts} ajout(s), {self.nb_cellules} cellule(s) mise(s) à jour, "
                f"{self.nb_adoptions} modif(s) humaine(s) respectée(s), "
                f"{self.nb_deplacees} déplacée(s), {self.nb_supprimees} suppression(s) constatée(s)")


def planifier(
    etat: dict,
    onglets: list[dict],
    candidats: list[tuple[str, ProgrammeExtrait, str]],
) -> Plan:
    """Cœur pur de la fusion à trois voies. Mute `etat` pour ce qui n'exige
    aucune écriture distante (suppressions, adoptions, déplacements) ; les
    écritures distantes sont retournées dans le Plan avec leurs mises à jour
    d'état différées."""
    resolution = resoudre_onglets(etat, onglets)
    localisation = _localiser_cles(onglets)
    lignes_etat: dict = etat.setdefault("lignes", {})
    plan = Plan()

    # Lignes que le robot connaît mais qui ont disparu du classeur → supprimées
    # à la main : on les retient pour ne jamais les ré-ajouter.
    for idu, entree in lignes_etat.items():
        if not entree.get("supprimee") and idu not in localisation:
            entree["supprimee"] = True
            plan.nb_supprimees += 1

    gid_a_classer = resolution.get(CATEGORIE_PAR_DEFAUT)

    for idu, programme, categorie in candidats:
        nouveau = ligne_classeur(programme)
        entree = lignes_etat.get(idu)
        position = localisation.get(idu)

        if position is None:
            if entree is not None:
                continue  # supprimée à la main (ou ajout précédent : voir plus haut)
            gid = resolution.get(categorie, gid_a_classer)
            if gid is None:
                plan.nb_sans_onglet += 1
                continue
            groupe = plan.ajouts.setdefault(gid, Ajouts(gid=gid))
            groupe.lignes.append(_rangee_avec_cle(nouveau, idu))
            groupe.entrees.append((idu, {
                "gid": gid, "valeurs": nouveau, "categorie": categorie, "supprimee": False,
            }))
            plan.nb_ajouts += 1
            continue

        gid, numero_ligne, rangee = position
        if entree is None:
            # Clé présente dans le classeur mais état perdu : on adopte la ligne
            # telle quelle comme nouvelle base, sans rien écrire.
            lignes_etat[idu] = {
                "gid": gid,
                "valeurs": [str(rangee[i]).strip() if i < len(rangee) else ""
                            for i in range(NB_COLONNES)],
                "categorie": categorie, "supprimee": False,
            }
            continue
        if entree.get("supprimee"):
            entree["supprimee"] = False  # la ligne est réapparue (annulation manuelle)
        if entree.get("gid") != gid:
            entree["gid"] = gid  # déplacée à la main : son nouvel onglet fait foi
            plan.nb_deplacees += 1

        base = [str(v).strip() for v in (entree.get("valeurs") or [])]
        base += [""] * (NB_COLONNES - len(base))
        courant = [str(rangee[i]).strip() if i < len(rangee) else ""
                   for i in range(NB_COLONNES)]

        cellules: list[dict] = []
        base_apres: list[str] = []
        for i in range(NB_COLONNES):
            if courant[i] != base[i]:
                base_apres.append(courant[i])       # modif humaine : elle gagne
                plan.nb_adoptions += 1
            elif nouveau[i] and nouveau[i] != base[i]:
                cellules.append({"ligne": numero_ligne, "colonne": i + 1,
                                 "valeur": nouveau[i]})
                base_apres.append(nouveau[i])       # cellule intacte : mise à jour
            else:
                base_apres.append(base[i])
        if cellules:
            groupe = plan.majs.setdefault(gid, Maj(gid=gid))
            groupe.cellules.extend(cellules)
            groupe.bases[idu] = base_apres
            plan.nb_cellules += len(cellules)
        else:
            entree["valeurs"] = base_apres          # adoption pure : état direct

    etat["onglets"] = {c: g for c, g in resolution.items()}
    return plan


# ─── Exécution via la passerelle ─────────────────────────────────────────────

def _lots(elements: list, taille: int):
    for debut in range(0, len(elements), taille):
        yield elements[debut:debut + taille]


def _envoyer_adaptatif(elements: list, envoyer_lot, taille_ref: list[int]) -> None:
    """Envoie `elements` par lots via `envoyer_lot(sous_liste)`.

    Si un lot est refusé parce que l'envoi n'est pas arrivé (réponse HTML — cas
    typique d'un antivirus/pare-feu qui inspecte le HTTPS et tronque les gros
    envois), la taille est divisée par deux et le même bloc est réessayé,
    jusqu'à une ligne. `taille_ref` est une liste [taille] partagée entre les
    onglets : la taille qui finit par passer sert directement aux suivants (on
    ne re-tâtonne qu'une fois). Lève ErreurAppScript si même un seul élément ne
    passe pas (blocage total, pas un simple problème de taille)."""
    indice, total = 0, len(elements)
    while indice < total:
        taille = min(taille_ref[0], total - indice)
        lot = elements[indice:indice + taille]
        try:
            envoyer_lot(lot)
        except ErreurAppScript as exc:
            if "n'a pas répondu en JSON" in str(exc) and taille > 1:
                taille_ref[0] = max(1, taille // 2)
                logger.info("Classeur : envoi réduit à %d élément(s)/lot (réseau limité)",
                            taille_ref[0])
                continue
            raise
        indice += taille


def synchroniser(config: Config, resultats: list[ResultatSource]) -> str:
    """Point d'entrée appelé par main : lit le classeur, planifie, exécute.
    Retourne un résumé d'une ligne pour le Journal."""
    url, jeton = config.classeur_appscript_url, config.classeur_appscript_jeton
    if not url or not jeton:
        raise RuntimeError(
            "Configuration du classeur incomplète : définir CLASSEUR_APPSCRIPT_URL "
            "et CLASSEUR_APPSCRIPT_TOKEN."
        )

    candidats: list[tuple[str, ProgrammeExtrait, str]] = []
    vus: set[str] = set()
    for resultat in resultats:
        for programme in resultat.programmes:
            idu = calculer_id_unique(programme.organisme, programme.nom_programme, programme.url)
            if idu in vus:
                continue
            vus.add(idu)
            candidats.append((idu, programme, categoriser(programme, resultat.source)))

    onglets = appeler_passerelle(url, jeton, "classeur_lire").get("onglets", [])
    if not onglets:
        raise RuntimeError("le classeur n'a renvoyé aucun onglet")

    etat = charger_etat()
    plan = planifier(etat, onglets, candidats)
    echecs = 0
    taille_ref = [TAILLE_LOT]  # partagée : ratchet de taille commun à tous les onglets

    # Mises à jour de cellules, onglet par onglet (l'état n'avance qu'après succès complet).
    for maj in plan.majs.values():
        def envoyer_cellules(lot, gid=maj.gid):
            appeler_passerelle(url, jeton, "classeur_maj", gid=gid, cellules=lot)
        try:
            _envoyer_adaptatif(maj.cellules, envoyer_cellules, taille_ref)
            for idu, base in maj.bases.items():
                etat["lignes"][idu]["valeurs"] = base
        except Exception as exc:  # l'état n'est pas avancé : nouvel essai demain
            echecs += 1
            logger.warning("Classeur : mise à jour de l'onglet gid=%s en échec : %s", maj.gid, exc)

    # Ajouts, onglet par onglet (l'état de chaque ligne n'avance qu'une fois écrite).
    for ajouts in plan.ajouts.values():
        paires = list(zip(ajouts.lignes, ajouts.entrees))  # (ligne, (idu, entrée d'état))

        def envoyer_lignes(lot, gid=ajouts.gid):
            appeler_passerelle(url, jeton, "classeur_ajouter", gid=gid,
                               lignes=[ligne for ligne, _ in lot])
            for _, (idu, entree) in lot:
                etat["lignes"][idu] = entree

        try:
            _envoyer_adaptatif(paires, envoyer_lignes, taille_ref)
        except Exception as exc:
            echecs += 1
            logger.warning("Classeur : ajout dans l'onglet gid=%s en échec : %s", ajouts.gid, exc)

    sauvegarder_etat(etat)
    resume = plan.resume()
    if plan.nb_sans_onglet:
        resume += f", {plan.nb_sans_onglet} sans onglet (« À classer » introuvable ?)"
    if taille_ref[0] < TAILLE_LOT:
        resume += f", envois réduits à {taille_ref[0]} ligne(s)/lot (réseau limité)"
    if echecs:
        resume += f", {echecs} appel(s) en échec (reprise au prochain passage)"
    return resume


# ─── Diagnostic de connexion ─────────────────────────────────────────────────

def _controler_url(nom_var: str, url: str | None, jeton: str | None) -> list[str]:
    """Affiche une URL telle qu'elle est lue et signale les défauts évidents."""
    if not url:
        print(f"  {nom_var} : ABSENTE")
        return ["absente"]
    print(f"  {nom_var} : [{url}]")
    print(f"     longueur : {len(url)} caractères ; jeton : "
          f"{'défini (' + str(len(jeton)) + ' car.)' if jeton else 'ABSENT'}")
    soupcons = []
    if not url.startswith("https://"):
        soupcons.append("ne commence pas par https://")
    if not url.endswith("/exec"):
        soupcons.append("ne se termine pas par /exec")
    if any(c.isspace() for c in url):
        soupcons.append("contient un espace ou un retour à la ligne (URL coupée ?)")
    if not jeton:
        soupcons.append("jeton absent")
    if soupcons:
        print("     ⚠ " + " ; ".join(soupcons))
    return soupcons


def _sonde_ecriture(url: str, jeton: str) -> bool:
    """Envoie des requêtes d'écriture de taille croissante vers un onglet
    inexistant (gid bidon : la passerelle répond « onglet introuvable » sans
    rien écrire). Repère à quelle taille les envois cessent de passer — signe
    d'un antivirus/pare-feu qui inspecte et tronque les gros envois HTTPS."""
    GID_BIDON = 999999999
    seuil_ok = 0
    premier_echec = None
    print("  sonde écriture (envois croissants, rien n'est écrit) :")
    for nb_lignes in (1, 20, 50, 100, 200):
        lignes = [["x" * 120 for _ in range(NB_COLONNES)] for _ in range(nb_lignes)]
        import json as _json
        ko = len(_json.dumps(lignes).encode()) // 1024
        try:
            # Onglet bidon → la passerelle répond « onglet introuvable » en JSON :
            # cette réponse PROUVE que l'envoi est bien arrivé (c'est un succès de
            # sonde). Seul un non-JSON (HTML) signale un envoi bloqué/tronqué.
            appeler_passerelle(url, jeton, "classeur_ajouter", gid=GID_BIDON, lignes=lignes)
            print(f"     {nb_lignes:3} lignes (~{ko:4} Ko) : OK (envoi arrivé)")
            seuil_ok = nb_lignes
        except ErreurAppScript as exc:
            if "n'a pas répondu en JSON" in str(exc):
                print(f"     {nb_lignes:3} lignes (~{ko:4} Ko) : ÉCHEC — envoi non arrivé (réponse HTML)")
                premier_echec = (nb_lignes, ko)
                break
            # Erreur JSON métier (« onglet introuvable ») = l'envoi est bien passé.
            print(f"     {nb_lignes:3} lignes (~{ko:4} Ko) : OK (envoi arrivé)")
            seuil_ok = nb_lignes
        except Exception:
            print(f"     {nb_lignes:3} lignes (~{ko:4} Ko) : ÉCHEC réseau")
            premier_echec = (nb_lignes, ko)
            break
    if premier_echec is None:
        return True
    nb, ko = premier_echec
    if seuil_ok == 0:
        print("     → même un petit envoi échoue : blocage réseau des écritures "
              "(antivirus/pare-feu/proxy qui inspecte le HTTPS ?).")
    else:
        print(f"     → les envois passent jusqu'à ~{seuil_ok} lignes puis cassent : "
              f"un antivirus/pare-feu tronque probablement les gros envois HTTPS.")
    print("     Piste : désactiver l'analyse HTTPS/SSL de l'antivirus pour "
          "script.google.com, ou réduire la taille des lots (réglage TAILLE_LOT).")
    return False


def _tester() -> int:
    """Vérifie les DEUX passerelles (Sheet principal + classeur) sans rien
    modifier : affiche chaque URL telle qu'elle est lue (révèle une coupure) et
    l'interroge depuis ce poste, pour identifier laquelle est en cause."""
    from .config import charger_config

    config = charger_config()
    cibles = [
        ("Sheet principal", "APPSCRIPT_URL", config.appscript_url, config.appscript_jeton, "structure"),
        ("Classeur", "CLASSEUR_APPSCRIPT_URL", config.classeur_appscript_url,
         config.classeur_appscript_jeton, "classeur_lire"),
    ]
    global_ok = True

    for libelle, nom_var, url, jeton, action in cibles:
        print(f"\n═ {libelle} ═")
        if not url:
            print(f"  {nom_var} : non configurée (cette destination est ignorée).")
            continue
        soupcons = _controler_url(nom_var, url, jeton)
        if any(s != "absente" for s in soupcons):
            print("     → corriger dans le .env (une seule ligne, sans espace) puis relancer.")
            global_ok = False
            continue
        try:
            rep = appeler_passerelle(url, jeton, "ping")
            print(f"  ping   : OK ({rep.get('reponse')})")
        except Exception as exc:
            print(f"  ping   : ÉCHEC — {exc}")
            global_ok = False
            continue
        try:
            reponse = appeler_passerelle(url, jeton, action)
            if action == "classeur_lire":
                onglets = reponse.get("onglets", [])
                print(f"  lecture: OK — {len(onglets)} onglet(s) lus")
                resolution = resoudre_onglets({"onglets": {}}, onglets)
                introuvables = [c for c in ONGLET_PAR_CATEGORIE if c not in resolution]
                if introuvables:
                    print(f"     ⚠ catégories sans onglet (iront dans « À classer ») : "
                          f"{', '.join(introuvables)}")
                # Sonde d'écriture : envois de taille croissante vers un onglet
                # BIDON (rien n'est écrit) pour repérer un blocage réseau des gros
                # envois (antivirus/pare-feu qui inspecte le HTTPS).
                if not _sonde_ecriture(url, jeton):
                    global_ok = False
            else:
                print("  lecture: OK")
        except Exception as exc:
            print(f"  lecture: ÉCHEC — {exc}")
            global_ok = False

    if global_ok:
        print("\n✓ Passerelles opérationnelles. Vous pouvez lancer la veille.")
        return 0
    print("\n✗ Au moins une passerelle est en échec — voir ci-dessus.")
    return 1


# ─── Petit utilitaire en ligne de commande ───────────────────────────────────

def principal(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="État local de la distribution vers le classeur manuel"
    )
    analyseur.add_argument("--resume", action="store_true",
                           help="afficher un résumé de l'état local")
    analyseur.add_argument("--tester", action="store_true",
                           help="diagnostiquer la connexion au classeur (lit le .env, "
                                "interroge la passerelle, ne modifie rien)")
    analyseur.add_argument("--reactiver", metavar="IDS",
                           help="ids (séparés par des virgules) de lignes supprimées à "
                                "ré-autoriser : elles seront ré-ajoutées à la prochaine collecte")
    args = analyseur.parse_args(argv)

    if args.tester:
        return _tester()

    etat = charger_etat()
    lignes = etat.get("lignes", {})

    if args.reactiver:
        demandes = [i.strip() for i in args.reactiver.split(",") if i.strip()]
        for idu in demandes:
            if idu in lignes:
                del lignes[idu]  # oubliée de l'état → re-traitée comme nouveauté
                print(f"réactivée : {idu}")
            else:
                print(f"inconnue : {idu}")
        sauvegarder_etat(etat)
        return 0

    supprimees = [i for i, e in lignes.items() if e.get("supprimee")]
    print(f"{len(lignes)} ligne(s) suivies, dont {len(supprimees)} supprimée(s) à la main")
    for idu in supprimees:
        entree = lignes[idu]
        print(f"  supprimée : {idu}  ({(entree.get('valeurs') or [''])[0][:60]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
