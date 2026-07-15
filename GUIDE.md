# Mode d'emploi — pas à pas, sans connaissances informatiques

Ce guide s'adresse à une personne qui **n'y connaît rien en informatique**. Il
explique, étape par étape, comment installer et faire fonctionner la veille des
subventions sur un ordinateur **Windows**. Prenez votre temps : comptez environ
**30 à 45 minutes** la première fois. Une fois installé, le programme travaille
tout seul chaque matin.

## À quoi sert ce programme ?

Chaque matin, il visite tout seul des dizaines de sites de subventions (CALQ,
Culture Mauricie, fondations, villes…) et recopie les programmes trouvés dans un
**tableau Google Sheets** — le même genre de tableau qu'Excel, mais en ligne.
Vous n'avez qu'à ouvrir ce tableau pour voir, d'un coup d'œil, les subventions
disponibles et leurs dates limites.

## Ce qu'il vous faut avant de commencer

- Un ordinateur **Windows** (allumé le matin, pour que le programme s'exécute).
- Un **compte Google** (une adresse Gmail suffit). Si vous n'en avez pas,
  créez-en un sur [google.com](https://google.com).
- Une **connexion Internet**.
- Ce guide, et un peu de patience pour l'étape 3 (la plus longue).

> **Important — vie privée.** Vous allez créer deux choses personnelles : un
> tableau et un « fichier-clé ». Elles n'appartiennent qu'à vous. Le code du
> programme, lui, est public sur Internet, mais **votre clé et votre tableau
> restent privés** : ne les envoyez à personne et ne les publiez nulle part. Le
> programme les garde sur votre ordinateur uniquement.

---

## Étape 1 — Télécharger le programme

1. Ouvrez la **page du projet sur GitHub** (le lien vous a été fourni ; c'est une
   page web dont l'adresse ressemble à `github.com/…/veille-subventions`).
2. Cherchez le bouton vert **« Code »**, cliquez dessus, puis sur
   **« Download ZIP »**.
3. Un fichier `.zip` se télécharge (souvent dans votre dossier
   **Téléchargements**). Faites un **clic droit** dessus → **« Extraire tout… »**
   → **« Extraire »**.
4. Vous obtenez un dossier. **Déplacez-le à un endroit stable et facile à
   retrouver**, par exemple `Documents\veille-subventions`. C'est votre dossier
   de travail ; on y reviendra à l'étape 4.

✅ *Vous devriez maintenant avoir un dossier contenant, entre autres, un fichier
nommé `lancer_veille.bat`.*

---

## Étape 2 — Créer votre tableau Google Sheets

1. Allez sur [sheets.google.com](https://sheets.google.com) et connectez-vous
   avec votre compte Google.
2. Cliquez sur **« + » (Feuille de calcul vierge)**. Un tableau vide s'ouvre.
3. Donnez-lui un nom, par exemple **« Veille subventions »** (cliquez sur
   « Feuille de calcul sans titre » en haut à gauche).
4. Repérez l'**adresse** (l'URL) de ce tableau, en haut de votre navigateur. Elle
   ressemble à :

   ```
   https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890/edit
   ```

   La longue suite de lettres et de chiffres entre `/d/` et `/edit` — ici
   `1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890` — s'appelle l'**identifiant du
   tableau** (le « SHEET_ID »). **Copiez-la** et gardez-la de côté (collez-la dans
   le Bloc-notes par exemple). On en aura besoin à l'étape 4.

✅ *Vous avez un tableau vide et son identifiant noté quelque part.*

---

## Étape 3 — Créer la « clé » qui autorise le programme à écrire dans votre tableau

C'est l'étape la plus longue, mais on ne la fait **qu'une seule fois**. Le but :
donner au programme un **laissez-passer** (un fichier) pour qu'il puisse remplir
votre tableau tout seul. En langage technique, ce laissez-passer s'appelle un
**« compte de service »**.

### 3a. Créer un projet Google Cloud (gratuit)

1. Allez sur [console.cloud.google.com](https://console.cloud.google.com) et
   connectez-vous avec le même compte Google.
2. Si c'est votre première visite, acceptez les conditions. **Aucune carte
   bancaire n'est demandée** pour ce que nous allons faire.
3. Tout en haut, cliquez sur le **sélecteur de projet** (à côté du logo « Google
   Cloud »), puis **« NOUVEAU PROJET »**. Nommez-le par exemple
   **« veille-subventions »** et cliquez **« CRÉER »**. Attendez quelques
   secondes, puis **sélectionnez ce projet** dans le même menu.

### 3b. Activer l'accès à Google Sheets

1. En haut, dans la barre de recherche, tapez **« Google Sheets API »** et
   cliquez sur le résultat.
2. Cliquez sur le bouton bleu **« ACTIVER »**. (Répétez au besoin avec
   **« Google Drive API »**.)

### 3c. Créer le compte de service (le laissez-passer)

1. Dans la barre de recherche, tapez **« Comptes de service »** (ou allez dans le
   menu ☰ → **« IAM et administration »** → **« Comptes de service »**).
2. Cliquez **« + CRÉER UN COMPTE DE SERVICE »**.
3. Donnez-lui un nom, par exemple **« robot-veille »**, puis **« CRÉER ET
   CONTINUER »**.
4. Les étapes « rôles » et « accès » sont facultatives : cliquez simplement sur
   **« CONTINUER »** puis **« OK »** (ou « TERMINER »).

### 3d. Télécharger le fichier-clé (JSON)

1. Vous voyez maintenant votre compte de service dans la liste. Il a une
   **adresse courriel** qui ressemble à
   `robot-veille@veille-subventions.iam.gserviceaccount.com`. **Copiez cette
   adresse** et gardez-la : on en a besoin à l'étape 3e.
2. Cliquez sur ce compte de service, puis sur l'onglet **« CLÉS »**.
3. Cliquez **« AJOUTER UNE CLÉ »** → **« Créer une clé »** → choisissez le format
   **JSON** → **« CRÉER »**.
4. Un fichier se télécharge automatiquement (dans **Téléchargements**). C'est
   **votre clé** — le laissez-passer du programme.
5. **Renommez ce fichier exactement `compte-service.json`**, puis **déplacez-le
   dans votre dossier de travail** (celui de l'étape 1, `Documents\veille-subventions`,
   à côté de `lancer_veille.bat`).

> ⚠️ **Ce fichier est un mot de passe.** Ne l'envoyez à personne, ne le publiez
> pas. S'il fuit, retournez dans l'onglet « CLÉS » et supprimez-le, puis créez-en
> un nouveau.

### 3e. Autoriser le compte de service sur votre tableau

C'est l'étape qu'on oublie souvent, et sans elle rien ne marche : il faut
**inviter le robot dans votre tableau**, comme vous inviteriez un collègue.

1. Retournez dans votre tableau Google Sheets (étape 2).
2. En haut à droite, cliquez sur le bouton **« Partager »**.
3. Collez l'**adresse courriel du compte de service** (copiée à l'étape 3d,
   celle en `…iam.gserviceaccount.com`).
4. Assurez-vous que le rôle est **« Éditeur »**, puis **« Envoyer »** (ignorez
   l'avertissement disant que ce n'est pas une vraie adresse).

✅ *Vous avez maintenant : le fichier `compte-service.json` dans votre dossier, et
votre tableau partagé avec le robot.*

---

## Étape 4 — Relier le tout

Le programme a besoin de savoir **quel tableau** remplir. On le lui dit dans un
petit fichier de réglages appelé **`.env`**.

1. Dans votre dossier de travail, **double-cliquez sur `lancer_veille.bat`**. Une
   fenêtre noire s'ouvre et le programme s'installe tout seul (il télécharge au
   besoin les outils nécessaires — cela peut prendre quelques minutes la première
   fois). **C'est normal.**
2. Au premier passage, il crée un fichier **`.env`** et vous demande de le
   remplir, puis s'arrête. **Ouvrez ce fichier `.env`** (clic droit → « Ouvrir
   avec » → **Bloc-notes**).
3. Complétez les deux lignes suivantes avec vos informations :

   ```
   SHEET_ID=collez-ici-l-identifiant-du-tableau-de-l-etape-2
   GOOGLE_SERVICE_ACCOUNT_FILE=compte-service.json
   ```

   (La deuxième ligne est probablement déjà correcte ; laissez-la telle quelle si
   votre fichier-clé s'appelle bien `compte-service.json`.)
4. **Enregistrez** le fichier `.env` (Fichier → Enregistrer) et fermez le
   Bloc-notes.

✅ *Le programme sait maintenant où écrire.*

---

## Étape 5 — Premier démarrage

1. **Préparez le tableau** (une seule fois) : ouvrez la fenêtre noire du
   programme. Le plus simple : dans votre dossier, maintenez la touche **Maj** et
   faites un **clic droit** dans une zone vide → **« Ouvrir la fenêtre PowerShell
   ici »** (ou « Invite de commandes »), puis tapez :

   ```
   lancer_veille.bat init
   ```

   Cela crée les onglets **Subventions**, **Journal** et **Archives** dans votre
   tableau, avec les couleurs. Retournez voir votre tableau : les onglets sont
   apparus.
2. **Lancez la première collecte** : **double-cliquez à nouveau sur
   `lancer_veille.bat`**. Le programme visite les sites (quelques minutes) et
   remplit votre tableau. À la fin, il affiche `Veille terminée`.
3. **Ouvrez votre tableau Google Sheets** : il est rempli de subventions ! 🎉

Au premier démarrage, le programme s'est aussi **programmé lui-même** pour se
relancer **chaque matin à 7 h**. Vous n'avez plus rien à faire.

---

## Au quotidien

- **Le matin**, si votre ordinateur est allumé, la veille s'exécute seule à 7 h
  et met le tableau à jour. Ouvrez simplement votre tableau pour voir les
  nouveautés (elles sont en **vert**, en haut).
- **Si l'ordinateur était éteint** à 7 h, pas de panique : **double-cliquez sur
  `lancer_veille.bat`** quand vous l'allumez. Le programme rattrape la journée
  sans jamais créer de doublons.
- **Pour vérifier que tout va bien** : dans le tableau, l'onglet **Journal** liste
  chaque exécution. Tant que la colonne **alertes** est vide, tout fonctionne. Si
  un site a changé et n'est plus lu, une alerte y apparaît — signalez-la à la
  personne technique, qui pourra réparer.

### Les couleurs du tableau

| Couleur | Signification |
|---|---|
| **Vert** | Subvention **nouvelle** (apparue à la dernière collecte) |
| **Orange** (colonne date limite) | Échéance dans **14 jours ou moins** — à traiter en priorité |
| **Gris** | Programme **expiré** (date limite passée) |

---

## En cas de problème

| Ce que vous voyez | Que faire |
|---|---|
| La fenêtre dit « SHEET_ID absent » | Le fichier `.env` n'est pas rempli. Reprenez l'étape 4. |
| Le tableau reste vide après l'exécution | Vérifiez que vous avez bien **partagé le tableau** avec l'adresse du compte de service (étape 3e) **en Éditeur**. |
| Erreur mentionnant « permission » ou « 403 » | Même cause : le partage du tableau (étape 3e) est manquant ou n'est pas en Éditeur. |
| « Python introuvable » puis blocage | Fermez la fenêtre et **relancez** `lancer_veille.bat` : Python vient d'être installé et sera visible au 2ᵉ lancement. |
| La fenêtre se ferme trop vite | Ce n'est rien : elle se ferme après la mention « terminée ». Ouvrez le tableau pour vérifier. |
| Ça ne s'exécute pas à 7 h | L'ordinateur doit être **allumé et la session ouverte** à cette heure. Sinon, double-cliquez sur le script dans la journée. |

Pour changer l'heure d'exécution : ouvrez `lancer_veille.bat` avec le Bloc-notes,
trouvez la ligne `set "HEURE=07:00"` et remplacez `07:00` par l'heure voulue
(format 24 h), enregistrez, puis relancez le script une fois.

---

## Petit lexique

- **Google Sheets** : un tableur en ligne (comme Excel), gratuit, dans votre
  navigateur.
- **SHEET_ID (identifiant du tableau)** : la longue suite de lettres/chiffres dans
  l'adresse de votre tableau ; elle désigne votre tableau de façon unique.
- **Compte de service** : un « utilisateur robot » qui permet au programme
  d'écrire dans votre tableau sans votre mot de passe personnel.
- **Fichier-clé (`compte-service.json`)** : le laissez-passer de ce robot. À
  garder secret.
- **`.env`** : le petit fichier de réglages où vous indiquez votre SHEET_ID.
- **Planificateur de tâches** : l'outil de Windows qui lance le programme
  automatiquement chaque matin.

---

*Une personne à l'aise avec l'informatique trouvera les détails techniques
(structure du code, ajout/réparation de sources, exécution sous macOS/Linux) dans
le fichier [README.md](README.md).*
