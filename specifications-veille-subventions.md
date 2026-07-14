# Spécifications — Système agentique de veille des subventions en art et culture

**Version :** 1.0
**Date :** 14 juillet 2026
**Statut :** À valider avant développement

---

## 1. Contexte et objectif

### 1.1 Besoin

Un organisme à but non lucratif (OBNL) culturel basé à Trois-Rivières (Mauricie, Québec), actif en **arts visuels / métiers d'art** et en **musique / arts de la scène**, souhaite recevoir **chaque matin** dans un **Google Sheet** la liste mise à jour des subventions disponibles dans son domaine.

### 1.2 Objectif du système

Un pipeline agentique autonome qui, une fois par jour :

1. Visite une liste de sources de financement (sites web gouvernementaux, régionaux, privés) ;
2. Extrait de façon structurée les programmes de subvention pertinents à l'aide d'un agent IA (API Claude avec outil de recherche web) ;
3. Filtre selon les critères d'admissibilité de l'organisme ;
4. Compare avec l'historique pour identifier les nouveautés et les programmes expirés ;
5. Met à jour le Google Sheet et signale les nouveautés.

### 1.3 Valeur ajoutée recherchée

- Ne plus manquer de date limite ni d'appel de projets régional.
- Voir immédiatement chaque matin ce qui est **nouveau** (tri par date de détection).
- Robustesse aux changements de mise en page des sites (avantage de l'approche agentique vs scraping classique).

### 1.4 Profil technique du responsable

Développeur autonome en **Python/JS**. Le langage retenu est **Python 3.11+**.

---

## 2. Sources à surveiller

### 2.1 Palier régional et municipal (priorité haute)

| Source | Page à surveiller | Notes |
|---|---|---|
| Culture Mauricie | `culturemauricie.ca/appels-de-dossiers` | Entente sectorielle de développement de la culture en Mauricie (appels de projets périodiques, fonds d'appui régional) |
| CALQ — Partenariat territorial Mauricie | `calq.gouv.qc.ca` (section partenariats territoriaux) | Appels à projets conjoints CALQ / MRC / villes |
| Ville de Trois-Rivières | `v3r.net` (section soutien aux organismes et artistes) | Programme de médiation culturelle, cadre de soutien au fonctionnement, soutien aux imprévus |

### 2.2 Palier provincial

| Source | Page à surveiller | Notes |
|---|---|---|
| CALQ — Programmes organismes | `calq.gouv.qc.ca/aide-financiere/programmes-daides-financiere/organismes` | Soutien à la programmation spécifique (dépôt en continu), diffusion, tournées, coproduction |
| MCC Québec | `quebec.ca/culture/aide-financiere` | Incluant l'Aide au fonctionnement pour les organismes culturels d'action communautaire |

### 2.3 Palier fédéral

| Source | Page à surveiller | Notes |
|---|---|---|
| Conseil des arts du Canada | `conseildesarts.ca` | Programmes Rayonner, Explorer et créer, Appuyer la pratique artistique |
| Patrimoine canadien | `canada.ca` (Fonds du Canada pour la présentation des arts, Fonds pour les espaces culturels) | |
| Musicaction / FACTOR | `musicaction.ca`, `factor.ca` | Volet musique |

### 2.4 Palier privé (phase ultérieure — v2)

Fondations régionales, Fonds du Grand Mouvement (Desjardins), portails Imagine Canada / Fundica. Plus difficile à scraper de façon fiable ; à intégrer après stabilisation des sources publiques.

> **Configuration** : les sources sont définies dans un fichier `sources.yaml` versionné, chacune avec : `nom`, `palier`, `url_principale`, `urls_secondaires`, `actif` (booléen). L'ajout d'une source ne doit exiger aucune modification de code.

---

## 3. Structure du Google Sheet

### 3.1 Onglet principal `Subventions`

| Colonne | Type | Description |
|---|---|---|
| `nom_programme` | texte | Nom officiel du programme |
| `organisme` | texte | CALQ, Culture Mauricie, Conseil des arts du Canada, etc. |
| `palier` | énum | Municipal / Régional / Provincial / Fédéral / Privé |
| `discipline` | texte | Arts visuels, métiers d'art, musique, arts de la scène, multi |
| `type` | énum | Fonctionnement / Projet / Immobilisation / Tournée / Autre |
| `montant` | texte | Montant max ou fourchette (ex. « jusqu'à 25 000 $ ») |
| `date_limite` | date ISO ou « continu » | AAAA-MM-JJ |
| `admissibilite_obnl` | énum | Oui / Non / À vérifier |
| `url` | URL | Lien direct vers la page du programme |
| `statut` | énum | Nouveau / Actif / Expiré |
| `date_detection` | date ISO | Première détection par l'agent |
| `derniere_verification` | date ISO | Dernier passage de l'agent |
| `notes_agent` | texte | Résumé IA en 2-3 phrases (objectifs, conditions clés) |
| `id_unique` | texte | Hash de `organisme + nom_programme` (clé de déduplication) |

### 3.2 Onglet `Journal`

Une ligne par exécution : `date`, `sources_visitées`, `sources_en_erreur`, `nouveautés_détectées`, `programmes_expirés`, `coût_api_estimé`, `durée_exécution`.

### 3.3 Règles d'affichage

- Tri par défaut : `statut` (Nouveau en premier), puis `date_limite` croissante.
- Mise en forme conditionnelle : lignes « Nouveau » en vert, dates limites à moins de 14 jours en orange, « Expiré » en gris.
- Les lignes « Expiré » sont conservées 90 jours puis archivées dans un onglet `Archives`.

---

## 4. Architecture agentique

### 4.1 Vue d'ensemble

```
[Planificateur quotidien (GitHub Actions cron)]
        │
        ▼
[1. Agent de collecte] ──► API Claude + outil web_search / web_fetch
        │  (1 appel par source, extraction JSON structurée)
        ▼
[2. Module de validation] ──► Pydantic (schéma strict, dates, URLs)
        │
        ▼
[3. Agent de déduplication/enrichissement] ──► comparaison avec l'état actuel du Sheet
        │
        ▼
[4. Écriture Google Sheets] ──► API Google Sheets (compte de service)
        │
        ▼
[5. Notification] ──► courriel récapitulatif (nouveautés + erreurs)
```

### 4.2 Composant 1 — Agent de collecte

- **Technologie** : API Anthropic Messages (`/v1/messages`), SDK Python `anthropic`.
- **Modèle recommandé** : `claude-sonnet-4-6` (bon rapport qualité/coût pour de l'extraction). Le nom du modèle doit être un paramètre de configuration.
- **Outil serveur** : `web_search` (type `web_search_20250305`, ou version plus récente avec filtrage dynamique si disponible), avec :
  - `max_uses: 5` par source ;
  - `allowed_domains` restreint au domaine de la source (évite la dérive et contrôle les coûts).
- Un appel API **par source** (isolation des erreurs : une source en panne ne bloque pas les autres).
- **Sortie exigée** : JSON strict (liste d'objets conformes au schéma de la section 3.1, sans `statut` ni dates de détection, qui sont gérés en aval). Le prompt exige « uniquement du JSON, sans préambule ni balises Markdown » ; le code retire néanmoins les éventuelles clôtures ``` avant parsing.

**Prompt d'extraction (canevas)** :

```
Tu es un agent de veille pour un OBNL culturel de la Mauricie (Québec),
actif en arts visuels, métiers d'art, musique et arts de la scène.

Visite {url_source} et ses pages de programmes de financement.
Extrais chaque programme de subvention ACTUELLEMENT OUVERT ou À VENIR qui :
- est accessible aux organismes à but non lucratif ;
- couvre les disciplines : arts visuels, métiers d'art, musique, arts de la scène ;
- couvre le territoire de la Mauricie ou l'ensemble du Québec/Canada ;
- a une date limite non échue (date du jour : {date_du_jour}) ou un dépôt en continu.

Réponds UNIQUEMENT avec un tableau JSON conforme à ce schéma : {schema_json}
Si aucun programme pertinent : réponds [].
Si une information est introuvable, utilise null — n'invente jamais.
```

### 4.3 Composant 2 — Validation

- Modèles **Pydantic** : rejet des entrées sans `nom_programme` ou `url` ; normalisation des dates (parsing tolérant → ISO) ; validation des URLs (même domaine que la source ou sous-domaine).
- Toute entrée invalide est journalisée mais n'interrompt pas le pipeline.
- Champ `admissibilite_obnl = "À vérifier"` si l'agent exprime une incertitude.

### 4.4 Composant 3 — Déduplication et cycle de vie

1. Lire l'état actuel du Sheet (toutes les lignes, indexées par `id_unique`).
2. Pour chaque programme extrait :
   - **Inconnu** → insertion avec `statut = Nouveau`, `date_detection = aujourd'hui`.
   - **Connu** → mise à jour de `derniere_verification` ; si `date_limite` a changé, mise à jour + note dans `notes_agent`.
3. Pour chaque ligne existante : si `date_limite < aujourd'hui` → `statut = Expiré`.
4. Les lignes `Nouveau` de la veille passent à `Actif` lors de l'exécution suivante.

### 4.5 Composant 4 — Écriture Google Sheets

- **Auth** : compte de service Google Cloud (clé JSON), Sheet partagé en édition avec le courriel du compte de service.
- **Librairie** : `gspread` (ou `google-api-python-client`).
- Écriture par lots (`batch_update`) pour limiter les appels.
- Aucune suppression destructive : uniquement insertions et mises à jour de statut.

### 4.6 Composant 5 — Notification

- Courriel quotidien (SMTP ou service transactionnel) envoyé **seulement si** : nouveautés détectées, OU erreurs de sources, OU échec global.
- Contenu : liste des nouveautés (nom, organisme, date limite, lien), sources en erreur, lien vers le Sheet.

---

## 5. Automatisation

- **Orchestrateur** : GitHub Actions, workflow `cron: "0 11 * * *"` (11h UTC ≈ 7h heure de l'Est ; noter la dérive d'une heure entre heure normale et heure avancée — acceptable, sinon deux crons saisonniers).
- **Secrets GitHub** : `ANTHROPIC_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON` (base64), `SHEET_ID`, `SMTP_*`.
- Déclenchement manuel possible (`workflow_dispatch`) pour les tests.
- Timeout global du job : 30 minutes.

---

## 6. Gestion des erreurs et fiabilité

| Situation | Comportement attendu |
|---|---|
| Source inaccessible / timeout | 2 relances avec backoff exponentiel, puis marquer la source en erreur dans le `Journal` et continuer |
| Réponse API non parsable en JSON | 1 relance avec message d'erreur explicite dans le prompt ; sinon journaliser et continuer |
| Erreur API Anthropic (429/529) | Backoff exponentiel, max 3 tentatives |
| Erreur Google Sheets | Sauvegarde locale des résultats en JSON (artefact GitHub Actions) + courriel d'alerte |
| Échec global | Le workflow échoue visiblement + courriel d'alerte |

**Garde-fous anti-hallucination** :
- Chaque programme inséré doit avoir une `url` valide du domaine source ;
- Les extractions incertaines sont marquées `À vérifier` (validation humaine légère durant la période de calibration) ;
- Aucune donnée existante n'est écrasée par une valeur `null`.

---

## 7. Coûts et contraintes

- **API Claude** : ~10-15 sources × 1 appel/jour avec `web_search` (5 recherches max/source). Recherche web facturée 10 $ / 1 000 recherches + jetons standards. Estimation : **5 à 20 $/mois**.
- **GitHub Actions** : gratuit (dépôt privé, largement sous le quota mensuel).
- **Google Sheets API** : gratuit à ce volume.
- **Respect des sites** : fréquence quotidienne unique, `max_uses` limité, pas de contournement de mesures anti-robots. Vérifier les conditions d'utilisation des sites au besoin.

---

## 8. Plan de livraison

| Jalon | Contenu | Critère de sortie |
|---|---|---|
| **J1 — Prototype** | Agent de collecte sur 3 sources (Culture Mauricie, CALQ organismes, Ville de Trois-Rivières), sortie JSON en console | Extraction correcte validée manuellement sur les 3 sources |
| **J2 — Intégration Sheet** | Validation Pydantic + déduplication + écriture Google Sheets | Le Sheet se remplit et se met à jour sans doublon sur 3 exécutions consécutives |
| **J3 — Automatisation** | GitHub Actions quotidien + journal + notification courriel | 5 jours consécutifs sans intervention |
| **J4 — Extension** | Ajout des sources fédérales et provinciales restantes ; mise en forme conditionnelle du Sheet | 10+ sources actives, taux d'erreur < 10 % |
| **v2 (ultérieur)** | Sources privées, filtrage par pertinence pondérée, résumé hebdomadaire | — |

---

## 9. Critères d'acceptation

1. Chaque matin avant 8h (heure de l'Est), le Sheet reflète l'état des sources actives de la veille au soir.
2. Une subvention nouvellement publiée sur une source active apparaît avec `statut = Nouveau` au plus tard le lendemain matin.
3. Aucun doublon (`id_unique` unique dans l'onglet `Subventions`).
4. Une source en panne n'empêche jamais la mise à jour des autres.
5. Aucun programme inséré sans URL valide pointant vers le domaine de sa source.
6. Le coût mensuel API reste sous 25 $ (alerte dans le `Journal` si dépassement projeté).

---

## 10. Hors périmètre (v1)

- Rédaction automatique des demandes de subvention.
- Surveillance intra-journalière (plus d'une exécution par jour).
- Sources nécessitant une authentification (portails membres).
- Interface web dédiée (le Google Sheet est l'interface).
