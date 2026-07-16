# Veille des subventions — art et culture (Mauricie)

Pipeline quotidien qui alimente un Google Sheet avec les subventions disponibles
pour un OBNL culturel de Trois-Rivières (arts visuels, métiers d'art, musique,
arts de la scène).

**v2 « scraping pur »** : aucune IA, aucun courriel, aucun secret d'API — du code
de scraping (requêtes HTTP + règles CSS) piloté par un catalogue JSON de
73 sources (municipal, régional, provincial, fédéral, privé). Chaque source y
est stockée avec sa ou ses règles d'extraction ; en ajouter ou en réparer une ne
demande aucun changement de code.

> 👉 **Vous n'êtes pas informaticien·ne et devez juste faire fonctionner l'outil ?**
> Suivez le **[mode d'emploi pas à pas (GUIDE.md)](GUIDE.md)**. Le présent README
> s'adresse aux personnes techniques ; les [spécifications](specifications-veille-subventions.md)
> décrivent l'architecture.

```
Planificateur de tâches Windows → lancer_veille.bat (chaque matin à 7 h, en local)
   │
   ▼
1. Scraping      — requests + BeautifulSoup, règles CSS par page (sources.json)
2. Validation    — Pydantic : champs obligatoires, dates → ISO, URL sur le domaine source
3. Déduplication — id_unique = hachage(organisme + nom_programme + chemin d'URL), statuts Nouveau/Actif/Expiré
4. Google Sheets — onglets Subventions / Journal / Archives, écriture par lots
```

## Contenu du dépôt

| Chemin | Rôle |
|---|---|
| `sources.json` | Catalogue des sources **avec leurs règles de scraping** — le cœur configurable |
| `veille/extracteur.py` | Moteur de scraping (téléchargement, moteur de règles CSS) — schéma des règles documenté en tête de fichier |
| `veille/models.py` | Validation Pydantic, normalisation des dates, `id_unique` |
| `veille/dedoublonnage.py` | Fusion avec l'état du Sheet, cycle de vie des statuts, archives, tri |
| `veille/feuille.py` | Lecture/écriture Google Sheets (gspread, compte de service) |
| `veille/feuille_appscript.py` | Lecture/écriture via la passerelle Apps Script (sans compte de service) |
| `appscript/Code.gs` | Le script à coller dans le Sheet (Extensions → Apps Script) |
| `veille/main.py` | Orchestrateur et point d'entrée CLI |
| `veille/config.py` | Configuration (variables d'environnement) |
| `scripts/initialiser_feuille.py` | Création des onglets + mise en forme conditionnelle (à lancer une fois) |
| `lancer_veille.bat` | **Windows** : installe tout (Python, dépendances), se planifie et exécute la veille |
| `lancer_veille.sh` | **Linux / cPanel** : équivalent du `.bat` (venv, cron, journaux) |
| `scripts/exporter_excel.py` | Essai visuel : collecte → fichier Excel local (sans Google Sheets) |
| `GUIDE.md` | **Mode d'emploi non technique** (installation pas à pas) |
| `specifications-veille-subventions.md` | Spécifications et architecture du système |
| `tests/` | Tests unitaires (moteur de règles, dates, déduplication, cycle de vie) |

## Le catalogue `sources.json`

Chaque source contient ses pages, et chaque page ses règles :

```json
{
  "id": "culture-mauricie",
  "nom": "Culture Mauricie",
  "palier": "Régional",
  "actif": true,
  "pages": [
    {
      "url": "https://culturemauricie.ca/appels-de-dossiers",
      "regles": {
        "bloc": "article.appel",
        "champs": {
          "nom_programme": "h2",
          "url": {"selecteur": "h2 a"},
          "date_limite": {"selecteur": ".date", "regex": "\\d{1,2} \\w+ \\d{4}"},
          "notes_agent": "p"
        },
        "exclure_si": ["(?i)archiv"]
      },
      "statut_regles": "testées 2026-07-14"
    }
  ]
}
```

- `bloc` : sélecteur CSS qui isole chaque programme ; `champs` : quoi extraire de
  chaque bloc (texte, attribut, regex, ou valeur fixe). Schéma complet documenté
  en tête de [veille/extracteur.py](veille/extracteur.py).
- `regles: null` = source cataloguée mais règles à écrire — elle est signalée au
  Journal à chaque exécution, sans bloquer les autres.
- Les dates sont normalisées automatiquement (« 1er avril 2026 » → `2026-04-01`,
  « dépôt en continu » → `continu`).

**Fragilité assumée** : quand un site change sa mise en page, sa règle casse. Le
système le signale (avertissement « 0 programme extrait » dans la colonne
`alertes` du Journal et dans les journaux d'exécution) et la réparation se fait
dans `sources.json`, sans toucher au code.

## Installation locale

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Essai rapide (sans Google Sheets)

```bash
python -m veille.main --console                          # toutes les sources actives
python -m veille.main --console --sources culture-mauricie
```

Les résultats de chaque collecte sont aussi sauvegardés dans
`sortie/resultats-AAAA-MM-JJ.json`.

**Vérification visuelle dans Excel** — pour voir le résultat final (mêmes
colonnes et tri que le futur Google Sheet) avant de brancher quoi que ce soit :

```bash
pip install openpyxl                                     # une seule fois (inclus dans [dev])
python scripts/exporter_excel.py                         # collecte fraîche → sortie/veille-subventions-AAAA-MM-JJ.xlsx
python scripts/exporter_excel.py --reprendre             # réutilise la dernière collecte, sans re-scraper
python scripts/exporter_excel.py --sources factor,calq-organismes
```

Le fichier contient l'onglet **Subventions** (900 lignes environ, échéances
proches surlignées en orange, liens cliquables, filtres) et l'onglet
**Journal** (détail par source : programmes, rejets, avertissements, erreurs).

## Configuration Google Sheets

Le Google Sheet reste l'interface de sortie. Deux façons de l'atteindre — l'une
ou l'autre, pas les deux :

### Option A (recommandée) — passerelle Apps Script, sans compte de service

Un petit script ([appscript/Code.gs](appscript/Code.gs)) se colle **dans** la
feuille et se déploie en « application Web » : le pipeline lui envoie les
données par HTTP avec un jeton partagé, et c'est lui qui écrit. Aucune console
Google Cloud, aucune clé JSON.

1. Ouvrir la feuille → **Extensions → Apps Script**, coller le contenu de
   `appscript/Code.gs`, remplacer le `JETON` par une phrase secrète.
2. **Déployer → Nouveau déploiement → Application Web** ; « Exécuter en tant
   que : Moi », « Qui peut accéder : Tout le monde ». Autoriser, copier l'URL
   `…/exec`.
3. Renseigner `.env` : `APPSCRIPT_URL=…/exec` et `APPSCRIPT_TOKEN=<la phrase>`.

Détail pas à pas avec captures d'écran mentales : [GUIDE.md](GUIDE.md), étape 3.
Après toute modification du script, **redéployer** (Gérer les déploiements →
Nouvelle version) — l'URL ne change pas. Le script utilise `LockService` :
deux exécutions simultanées ne peuvent pas se marcher dessus.

### Option B — compte de service Google Cloud (clé JSON)

1. [console.cloud.google.com](https://console.cloud.google.com) : créer un projet
   (gratuit, sans facturation), puis activer l'**API Google Sheets**
   (menu « API et services → Bibliothèque »).
2. « IAM et administration → Comptes de service » : créer un compte de service
   (ex. `veille-subventions`), puis onglet **Clés → Ajouter une clé → JSON**.
   Enregistrer le fichier téléchargé **à la racine du projet** sous le nom
   `compte-service.json` (il est exclu de git et n'est jamais publié).
3. Créer le Google Sheet (vide), noter son `SHEET_ID` (la longue chaîne dans
   l'URL) et **partager la feuille en édition** avec l'adresse courriel du
   compte de service (`...@...iam.gserviceaccount.com`).
4. Renseigner le fichier `.env` : `SHEET_ID=...` et
   `GOOGLE_SERVICE_ACCOUNT_FILE=compte-service.json`.

Le pipeline choisit tout seul : si `APPSCRIPT_URL` est défini, il passe par la
passerelle ; sinon par le compte de service.

## Exécution quotidienne — en local sous Windows

Tout tourne sur le poste de l'organisme, sans aucun service infonuagique :
[lancer_veille.bat](lancer_veille.bat) s'occupe de tout.

**Mise en route (une seule fois) :**

1. Copier le dossier du projet sur le poste Windows.
2. Double-cliquer `lancer_veille.bat`. Le script :
   - s'enregistre dans le **Planificateur de tâches Windows** (tous les jours à
     7 h — réglable via `HEURE` en tête de script) ;
   - installe **Python** via winget s'il est absent ;
   - crée l'environnement virtuel `.venv-windows` et installe les dépendances ;
   - crée `.env` à partir du modèle au premier passage — le remplir (voir
     section précédente), puis relancer.
3. Initialiser le Sheet (onglets + mise en forme conditionnelle) :
   `lancer_veille.bat init`
4. Relancer `lancer_veille.bat` : la première collecte remplit la feuille.

**Au quotidien :** la tâche `VeilleSubventions` s'exécute chaque matin à 7 h si
le poste est **allumé et la session ouverte** ; sinon, un double-clic rattrape
la journée (la déduplication rend les exécutions répétées sans danger). La
sortie de chaque exécution planifiée est consignée dans `journaux\veille-AAAA-MM-JJ.log`
(60 jours de rétention), en plus de l'onglet Journal du Sheet.

Commandes utiles :

```bat
lancer_veille.bat                          :: exécution manuelle immédiate
schtasks /Run /TN VeilleSubventions        :: déclencher la tâche planifiée
schtasks /Delete /TN VeilleSubventions /F  :: désinstaller la planification
```

**Surveillance sans courriel** : les échecs sont visibles dans
`journaux\` et dans l'onglet Journal du Sheet (sources en erreur, alertes
« 0 programme extrait », sources dont les règles restent à écrire).

## Déploiement serveur — Linux / cPanel

Sur un hébergement cPanel, le projet tourne comme **tâche cron**, pas comme site
web. Placez le dossier **hors de `public_html`** : `.env` (et l'éventuel
`compte-service.json`) sont des secrets. [lancer_veille.sh](lancer_veille.sh)
est l'équivalent Linux du `.bat` : il trouve un Python 3.11+ (y compris les
chemins CloudLinux `/opt/alt/python3xx`), crée `.venv`, installe les
dépendances, charge `.env` et journalise dans `journaux/`.

Mise en route, en SSH depuis le dossier du projet :

```bash
chmod +x lancer_veille.sh
./lancer_veille.sh              # 1er passage : installe tout, crée .env → le remplir
./lancer_veille.sh init         # une fois : onglets + mise en forme du Sheet
./lancer_veille.sh              # collecte immédiate (vérification)
./lancer_veille.sh planifier    # inscrit la tâche cron quotidienne (7 h)
```

Sans accès SSH : dans **cPanel → Tâches Cron**, ajoutez une tâche quotidienne
(minute `0`, heure `7`) avec la commande :

```
/bin/bash /home/VOTRE_COMPTE/veille-subventions/lancer_veille.sh tache
```

Le mode `tache` envoie toute la sortie dans `journaux/veille-AAAA-MM-JJ.log`
(60 jours de rétention). Adaptez le chemin à celui affiché par le gestionnaire
de fichiers cPanel. L'heure du cron suit le fuseau du serveur — décalez-la au
besoin. Avec l'option A (Apps Script), aucun fichier de clé n'est à déposer sur
le serveur : `.env` suffit.

> Sur macOS, l'équivalent manuel reste disponible : `./lancer_veille.sh`
> fonctionne aussi (ou `python -m veille.main`), à planifier via `launchd`.

## Réparer ou ajouter une source

1. Repérer la panne : colonne `alertes` du Journal (« 0 programme extrait ») ou
   journaux d'exécution.
2. Télécharger la page : `curl -sL -A "Mozilla/5.0" <url> -o page.html`, examiner
   la nouvelle structure HTML.
3. Ajuster les sélecteurs dans `sources.json`, puis tester localement :
   `python -m veille.main --console --sources <id>`.
4. C'est tout — la prochaine exécution (planifiée ou `lancer_veille.bat`) utilise
   le `sources.json` modifié, sans redéploiement.

Pour ajouter une source : nouvelle entrée dans `sources.json` (au besoin avec
`"regles": null` le temps d'écrire les sélecteurs). Les sites qui n'affichent
leur contenu qu'en JavaScript sont marqués `"statut_regles": "js_requis"` et
demandent soit leur API JSON interne (documentée dans la règle quand elle
existe), soit un navigateur sans tête (non inclus en v2).

## Tests

```bash
pytest
```
