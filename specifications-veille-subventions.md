# Spécifications — Système de veille des subventions en art et culture

**Version :** 2.0 — « scraping pur »
**Date :** 15 juillet 2026
**Statut :** Livré, en exploitation locale

> **Historique.** La version 1.0 (14 juillet 2026) décrivait un système *agentique*
> : extraction par intelligence artificielle (API Claude + recherche web),
> orchestration GitHub Actions, notification par courriel. Cette approche a été
> **entièrement remplacée** à la demande du responsable par un scraping pur, sans
> IA, sans courriel et sans hébergement infonuagique. Le présent document décrit
> le système réellement construit ; le mode d'emploi pas-à-pas pour une personne
> non technicienne se trouve dans [GUIDE.md](GUIDE.md).

---

## 1. Contexte et objectif

### 1.1 Besoin

Un organisme à but non lucratif (OBNL) culturel basé à Trois-Rivières (Mauricie,
Québec), actif en **arts visuels / métiers d'art** et en **musique / arts de la
scène**, souhaite retrouver **chaque matin** dans un **Google Sheet** la liste à
jour des subventions disponibles.

### 1.2 Objectif du système

Un programme autonome qui, une fois par jour et **en local** :

1. Visite une liste de pages de financement définies dans un catalogue ;
2. En extrait les programmes de subvention par **scraping** (règles CSS, sans IA) ;
3. Valide et normalise les données (champs obligatoires, dates, URL) ;
4. Compare avec l'état de la veille pour distinguer nouveautés et programmes expirés ;
5. Met à jour le Google Sheet (onglets Subventions, Journal, Archives).

### 1.3 Parti pris de conception

- **Aucune dépendance payante ni clé d'API.** Le seul service externe est le
  Google Sheet de sortie (gratuit).
- **Le savoir spécifique aux sites vit dans les données, pas dans le code.**
  Chaque page a ses règles de scraping en JSON ; ajouter ou réparer une source
  ne demande aucune modification de code (voir §2 et §4.2).
- **Fragilité assumée et signalée.** Contrairement à l'approche IA, un scraper
  casse quand un site change sa mise en page. Le système le détecte
  (avertissement « 0 programme extrait ») et l'affiche au Journal ; la réparation
  se fait dans le catalogue.

### 1.4 Profil technique du responsable

Développeur autonome en **Python / JS**. Langage retenu : **Python 3.11+**.
L'exploitation quotidienne, elle, ne demande **aucune compétence technique**
(voir [GUIDE.md](GUIDE.md)).

---

## 2. Sources à surveiller

Le catalogue compte **73 sources** (71 actives), du palier municipal au privé,
réparties ainsi : 23 provinciales, 19 privées/fondations, 13 fédérales,
11 régionales, 5 municipales. Il couvre notamment CALQ, MCC, SODEC, Conseil des
arts du Canada, Patrimoine canadien, Musicaction, FACTOR, Culture Mauricie,
Ville de Trois-Rivières, les MRC de la Mauricie, de nombreuses fondations, et —
depuis l'enrichissement du 15 juillet 2026 — des sources hors culture stricte
(Ville de Montréal, Conseil des arts de Montréal, tourisme, agriculture,
environnement, économie sociale, innovation) intégrées à la demande du
responsable pour une couverture maximale.

### 2.1 Le catalogue `sources.json`

Toutes les sources sont définies dans le fichier **`sources.json`** (versionné),
qui est le cœur configurable du système. Chaque source contient :

| Champ | Rôle |
|---|---|
| `id` | Identifiant court et stable |
| `nom` | Nom lisible de l'organisme |
| `palier` | Municipal / Régional / Provincial / Fédéral / Privé |
| `actif` | Booléen ; une source inactive n'est jamais visitée |
| `pages` | Liste de pages, **chacune avec ses règles de scraping** |
| `domaines_supplementaires` | Domaines autorisés en plus de celui de la source |
| `notes` | Particularités, décisions, admissibilité géographique |

Chaque page porte : `url`, `regles` (le schéma de scraping — voir §4.2, documenté
en tête de `veille/extracteur.py`), et `statut_regles` (« testées AAAA-MM-JJ »,
« js_requis — … », etc.). Une page dont la liste n'est rendue qu'en JavaScript
est marquée `js_requis` et laissée sans règle : elle est signalée mais ne bloque
personne.

---

## 3. Structure du Google Sheet

### 3.1 Onglet principal `Subventions`

14 colonnes :

| Colonne | Type | Description |
|---|---|---|
| `nom_programme` | texte | Nom du programme |
| `organisme` | texte | CALQ, Culture Mauricie, etc. |
| `palier` | énum | Municipal / Régional / Provincial / Fédéral / Privé |
| `discipline` | texte | Arts visuels, métiers d'art, musique, arts de la scène, multi… |
| `type` | énum | Fonctionnement / Projet / Immobilisation / Tournée / Autre |
| `montant` | texte | Montant max ou fourchette (ex. « jusqu'à 25 000 $ ») |
| `date_limite` | date ISO ou « continu » | AAAA-MM-JJ |
| `admissibilite_obnl` | énum | Oui / Non / À vérifier |
| `url` | URL | Lien direct vers la page du programme |
| `statut` | énum | Nouveau / Actif / Expiré |
| `date_detection` | date ISO | Première détection |
| `derniere_verification` | date ISO | Dernier passage du robot |
| `notes_agent` | texte | Détails extraits de la page |
| `id_unique` | texte | Clé de déduplication (voir §4.4) |

### 3.2 Onglet `Journal`

Une ligne par exécution : `date`, `sources_visitées`, `sources_en_erreur`,
`nouveautés_détectées`, `programmes_expirés`, `coût_api_estimé` (toujours
« 0 $ (scraping) »), `durée_exécution`, **`alertes`** (sources dont la règle n'a
rien extrait, règles à écrire — c'est ici qu'on repère une source à réparer).

### 3.3 Règles d'affichage

- Tri par défaut : `statut` (Nouveau en premier), puis `date_limite` croissante,
  puis « continu », puis sans date.
- Mise en forme conditionnelle : lignes « Nouveau » en vert, dates limites à
  moins de 14 jours en orange, « Expiré » en gris.
- Les lignes « Expiré » sont conservées 90 jours puis déplacées dans l'onglet
  `Archives`.

L'initialisation des onglets et de la mise en forme se fait une seule fois via
`scripts/initialiser_feuille.py` (ou `lancer_veille.bat init`).

---

## 4. Architecture

### 4.1 Vue d'ensemble

```
[Planificateur de tâches Windows — chaque matin à 7 h, en local]
        │
        ▼
[1. Scraping]        requests + BeautifulSoup, règles CSS par page (sources.json)
        │            1 collecte par source ; une source en panne n'arrête pas les autres
        ▼
[2. Validation]      Pydantic : champs obligatoires, dates → ISO, URL sur le domaine
        │
        ▼
[3. Déduplication]   comparaison avec l'état du Sheet, cycle de vie des statuts
        │
        ▼
[4. Écriture Sheets] gspread + compte de service ; écriture par lots, sans suppression
```

Aucune étape n'appelle d'IA ; aucune notification par courriel (les alertes
passent par l'onglet Journal et les journaux locaux).

### 4.2 Composant 1 — Moteur de scraping

- **Technologie** : `requests` (téléchargement, 3 tentatives, backoff exponentiel,
  30 s de délai, en-tête `User-Agent` identifiant la veille) + `BeautifulSoup`
  (`lxml`).
- **Moteur de règles** piloté par `sources.json`. Schéma d'une règle :
  - `bloc` : sélecteur CSS isolant chaque programme (absent = la page entière est
    un programme unique) ;
  - `champs` : pour chaque colonne, un sélecteur (chaîne) ou un objet
    `{selecteur, attribut, regex, valeur, titre_depuis_slug}`. `valeur` fixe une
    constante (ex. l'organisme) ; `regex` garde le groupe 1 ; `titre_depuis_slug`
    reconstruit un libellé lisible à partir d'un identifiant d'URL (repli sur le
    plan de site quand la page-liste est en JavaScript) ;
  - `exclure_si` : liste de regex sur `nom_programme` pour écarter le bruit.
- Pour le champ `url`, l'attribut `href` est pris par défaut sur un lien et les
  URL relatives sont résolues en absolu.
- **Détection d'encodage** : si l'en-tête HTTP n'annonce pas de charset, on se
  fie au contenu (`apparent_encoding`) pour éviter les accents corrompus.

### 4.3 Composant 2 — Validation

- Modèles **Pydantic** : rejet des entrées sans `nom_programme` ou `url` ;
  normalisation tolérante des dates françaises → ISO (« 1er avril 2026 » →
  `2026-04-01`, « en continu » → `continu`) ; **garde-fou de domaine** (une URL
  hors du domaine de la source, ou de ses `domaines_supplementaires`, est rejetée).
- Toute entrée invalide est journalisée sans interrompre le pipeline.
- `admissibilite_obnl` vaut « À vérifier » par défaut.

### 4.4 Composant 3 — Déduplication et cycle de vie

- **Clé `id_unique`** = hachage de `organisme + nom_programme + chemin d'URL`
  (sans les paramètres de requête). L'inclusion du chemin distingue des volets
  homonymes d'un même organisme (ex. les partenariats territoriaux du CALQ).
- **Cycle de vie** :
  - Programme inconnu → `Nouveau`, `date_detection = aujourd'hui` ;
  - Programme connu → `derniere_verification` mise à jour ; si `date_limite`
    change, mise à jour (jamais d'écrasement par une valeur vide) ;
  - `date_limite` passée → `Expiré` ;
  - Une ligne `Nouveau` de la veille passe à `Actif` le lendemain ;
  - `Expiré` depuis plus de 90 jours → onglet `Archives`.

### 4.5 Composant 4 — Écriture Google Sheets

Deux canaux interchangeables (choisis par la configuration, même interface) :

- **Passerelle Apps Script (par défaut recommandé)** : un script
  (`appscript/Code.gs`) est collé dans la feuille et déployé en application
  Web ; le pipeline (`veille/feuille_appscript.py`) lui envoie les données par
  HTTP, authentifiées par un jeton partagé (`APPSCRIPT_URL` +
  `APPSCRIPT_TOKEN`). Aucun compte de service ni clé JSON ; le script est
  verrouillé (`LockService`) contre les exécutions simultanées et ne touche
  qu'à la feuille qui l'héberge.
- **Compte de service Google Cloud** (`veille/feuille.py`, librairie `gspread`) :
  clé JSON + Sheet partagé en édition avec le courriel du compte de service
  (`SHEET_ID` + `GOOGLE_SERVICE_ACCOUNT_FILE`).

Dans les deux cas : écriture par lots, aucune suppression destructive, et une
sauvegarde JSON locale (`sortie/resultats-AAAA-MM-JJ.json`) précède toujours
l'écriture — filet de sécurité si le Sheet est indisponible.

---

## 5. Automatisation — deux modes d'exécution

### 5.1 Serveur Linux / cPanel (mode retenu)

- **Orchestrateur** : une **tâche cron** quotidienne (7 h) appelant
  `lancer_veille.sh tache` — soit inscrite automatiquement
  (`./lancer_veille.sh planifier`), soit ajoutée dans le menu « Tâches Cron »
  de cPanel.
- **Amorçage autonome** : `lancer_veille.sh` détecte un Python 3.11+ (y compris
  les chemins CloudLinux `/opt/alt/python3xx`), crée `.venv`, installe les
  dépendances, crée `.env` à partir du modèle au premier passage.
- **Journaux** : mode `tache` → `journaux/veille-AAAA-MM-JJ.log` (60 jours de
  rétention).
- Le dossier du projet doit rester **hors de `public_html`** (le `.env` est un
  secret). Avec la passerelle Apps Script, aucun fichier de clé n'est déposé
  sur le serveur.

### 5.2 Poste Windows (alternative locale)

- **Orchestrateur** : le **Planificateur de tâches Windows**, alimenté par
  `lancer_veille.bat`, qui s'auto-enregistre (tâche quotidienne à 7 h, heure
  réglable) et installe Python (winget) + `.venv-windows` au besoin.
- **Rattrapage** : si le poste était éteint à 7 h, un double-clic refait la
  collecte du jour ; la déduplication rend les ré-exécutions sans danger.

### 5.3 Configuration commune (fichier `.env`)

`APPSCRIPT_URL` + `APPSCRIPT_TOKEN` (passerelle Apps Script, recommandé) **ou**
`SHEET_ID` + `GOOGLE_SERVICE_ACCOUNT_FILE` (compte de service). Réglages
facultatifs : `JOURS_RETENTION_EXPIRES`, `DELAI_ENTRE_REQUETES_S`.

---

## 6. Gestion des erreurs et fiabilité

| Situation | Comportement attendu |
|---|---|
| Source inaccessible / timeout | 3 tentatives avec backoff exponentiel, puis marquer la source en erreur au Journal et continuer |
| Règle qui n'extrait plus rien (mise en page changée) | Avertissement « 0 programme extrait » dans la colonne `alertes` du Journal ; la source est à réparer dans `sources.json` |
| Donnée invalide (sans nom/URL, hors domaine) | Entrée rejetée et journalisée ; le pipeline continue |
| Erreur Google Sheets | Résultats déjà sauvegardés en JSON local ; l'erreur est journalisée |
| Toutes les sources en panne | Code de sortie en échec (visible dans le journal du jour) |

**Garde-fous** : chaque programme inséré a une URL valide du domaine de sa source ;
aucune donnée existante n'est écrasée par une valeur vide ; les extractions
incertaines restent « À vérifier ».

---

## 7. Coûts et contraintes

- **Aucun coût d'API** : plus d'IA, plus de recherche web facturée. Le Journal
  affiche « 0 $ ».
- **Google Sheets API** : gratuit à ce volume.
- **Hébergement** : aucun — le programme tourne sur le poste de l'organisme.
  Seul coût : l'électricité du poste, qui doit être allumé à l'heure planifiée.
- **Respect des sites** : une seule visite par jour, délai d'une seconde entre
  requêtes, `User-Agent` explicite, aucun contournement de mesures anti-robots.

---

## 8. État de livraison

| Jalon | Contenu | État |
|---|---|---|
| Moteur de scraping + règles CSS externalisées | `veille/extracteur.py`, `sources.json` | ✅ livré |
| Validation Pydantic + déduplication + cycle de vie | `veille/models.py`, `veille/dedoublonnage.py` | ✅ livré |
| Écriture Google Sheets + initialisation | `veille/feuille.py`, `scripts/initialiser_feuille.py` | ✅ livré |
| Passerelle Apps Script (sans compte de service) | `appscript/Code.gs`, `veille/feuille_appscript.py` | ✅ livré |
| Catalogue 73 sources (couverture maximale) | `sources.json` | ✅ livré |
| Exécution serveur Linux / cPanel (cron) | `lancer_veille.sh` | ✅ livré |
| Exécution locale Windows auto-installante | `lancer_veille.bat` | ✅ livré (non testé sur Windows) |
| Essai visuel Excel | `scripts/exporter_excel.py` | ✅ livré |
| Tests unitaires | `tests/` | ✅ 19 tests |

**Vérifié le 15 juillet 2026** (collecte réelle) : 996 programmes bruts →
909 lignes uniques, 0 source en erreur.

**Restant côté organisme** (voir [GUIDE.md](GUIDE.md)) : créer le Google Sheet,
y coller et déployer la passerelle Apps Script, remplir `.env`, puis lancer
`lancer_veille.sh` sur le serveur (ou `lancer_veille.bat` sur un poste Windows).

---

## 9. Critères d'acceptation

1. Chaque matin, le Sheet reflète l'état des sources actives de la veille au soir
   (si le poste était allumé ; sinon, rattrapage par double-clic).
2. Une subvention nouvellement publiée sur une source active apparaît en
   `Nouveau` au plus tard le lendemain.
3. Aucun doublon (`id_unique` unique dans l'onglet `Subventions`).
4. Une source en panne n'empêche jamais la mise à jour des autres.
5. Aucun programme inséré sans URL valide pointant vers le domaine de sa source.
6. Aucun coût récurrent.

---

## 10. Hors périmètre

- Rédaction automatique des demandes de subvention.
- Filtrage automatique par admissibilité géographique fine (la couverture est
  volontairement large ; le tri se fait à l'œil dans le Sheet, aidé par les
  colonnes `palier` et `notes`).
- Surveillance intra-journalière (une seule exécution par jour).
- Sources nécessitant une authentification ou un rendu JavaScript (marquées
  `js_requis`, laissées sans règle).
- Interface web dédiée (le Google Sheet est l'interface).
