# Mode d'emploi — pas à pas, sans connaissances informatiques

Ce guide s'adresse à une personne qui **n'y connaît rien en informatique**. Il
explique, étape par étape, comment installer et faire fonctionner la veille des
subventions. Prenez votre temps : comptez environ **30 minutes** la première
fois. Une fois installé, le programme travaille tout seul chaque matin.

## À quoi sert ce programme ?

Chaque matin, il visite tout seul des dizaines de sites de subventions (CALQ,
Culture Mauricie, fondations, villes…) et recopie les programmes trouvés dans un
**tableau Google Sheets** — le même genre de tableau qu'Excel, mais en ligne.
Vous n'avez qu'à ouvrir ce tableau pour voir, d'un coup d'œil, les subventions
disponibles et leurs dates limites.

## Ce qu'il vous faut avant de commencer

- Un **compte Google** (une adresse Gmail suffit). Si vous n'en avez pas,
  créez-en un sur [google.com](https://google.com).
- Une **connexion Internet**.
- Un endroit où le programme s'exécutera chaque matin : votre **ordinateur
  Windows**, ou un **serveur** géré par votre personne technique. *Si une
  personne technique héberge le robot pour vous, vous n'avez à faire que les
  étapes 2 et 3 — donnez-lui ensuite l'adresse et la phrase secrète obtenues à
  l'étape 3, et c'est tout.*

> **Important — vie privée.** Le code du programme est public sur Internet, mais
> **votre tableau et votre phrase secrète restent privés** : ne les publiez
> nulle part et ne les partagez qu'avec votre personne de confiance.

---

## Étape 1 — Télécharger le programme

*(À sauter si une personne technique installe le robot pour vous.)*

1. Ouvrez la **page du projet sur GitHub** (le lien vous a été fourni ; l'adresse
   ressemble à `github.com/…/Subventions-robot-art-culture`).
2. Cherchez le bouton vert **« Code »**, cliquez dessus, puis sur
   **« Download ZIP »**.
3. Un fichier `.zip` se télécharge (souvent dans **Téléchargements**). Faites un
   **clic droit** dessus → **« Extraire tout… »** → **« Extraire »**.
4. Vous obtenez un dossier. **Déplacez-le à un endroit stable**, par exemple
   `Documents\veille-subventions`.

✅ *Vous devriez avoir un dossier contenant, entre autres, `lancer_veille.bat`
(pour Windows) et un sous-dossier `appscript`.*

---

## Étape 2 — Créer votre tableau Google Sheets

1. Allez sur [sheets.google.com](https://sheets.google.com) et connectez-vous
   avec votre compte Google.
2. Cliquez sur **« + » (Feuille de calcul vierge)**. Un tableau vide s'ouvre.
3. Donnez-lui un nom, par exemple **« Veille subventions »** (cliquez sur
   « Feuille de calcul sans titre » en haut à gauche).

✅ *Vous avez un tableau vide. Gardez-le ouvert : l'étape 3 se passe dedans.*

---

## Étape 3 — Installer le « facteur » dans votre tableau

Le programme ne touche jamais directement à votre tableau : il remet les données
à un petit **script-facteur** qui habite *dans* le tableau et qui écrit à sa
place. Pour l'installer, c'est un simple **copier-coller** — aucune console
technique, aucune carte bancaire, rien à télécharger.

### 3a. Coller le script dans le tableau

1. Dans votre tableau, ouvrez le menu **Extensions** → **Apps Script**. Un
   nouvel onglet s'ouvre avec un éditeur contenant quelques lignes
   (`function myFunction()…`).
2. **Effacez tout** le contenu de l'éditeur.
3. Ouvrez le fichier **`appscript/Code.gs`** du dossier du programme (clic droit
   → « Ouvrir avec » → **Bloc-notes**), **sélectionnez tout** (Ctrl+A),
   **copiez** (Ctrl+C), puis **collez** (Ctrl+V) dans l'éditeur Apps Script.
   *(Si une personne technique installe le robot, elle peut aussi vous envoyer
   ce fichier par courriel.)*

### 3b. Choisir votre phrase secrète

1. Vers le haut du script collé, repérez la ligne :

   ```
   const JETON = "CHANGEZ-MOI";
   ```

2. Remplacez `CHANGEZ-MOI` par une **phrase secrète de votre invention** (gardez
   les guillemets), par exemple :

   ```
   const JETON = "tournesol-83-ruisseau";
   ```

3. **Notez cette phrase** quelque part : on la redonne au robot à l'étape 4.
4. Cliquez sur l'icône **💾 (Enregistrer)** en haut de l'éditeur.

### 3c. Mettre le facteur en service (« déployer »)

1. En haut à droite de l'éditeur, cliquez sur le bouton bleu **« Déployer »** →
   **« Nouveau déploiement »**.
2. Cliquez sur la **roue dentée** (⚙️) à gauche → choisissez **« Application
   Web »**.
3. Réglez les deux choix ainsi :
   - **Exécuter en tant que : Moi** (votre adresse) ;
   - **Qui peut accéder : Tout le monde**. *(Rassurez-vous : « tout le monde »
     ne peut rien faire sans votre phrase secrète.)*
4. Cliquez **« Déployer »**.
5. Google demande une autorisation (normal : le script écrira dans votre
   tableau). Cliquez **« Autoriser l'accès »**, choisissez votre compte. Si un
   écran dit « Google n'a pas validé cette application », cliquez sur
   **« Paramètres avancés »** puis **« Accéder à … (non sécurisé) »** — c'est
   *votre propre script*, il n'y a aucun danger — puis **« Autoriser »**.
6. À la fin, Google affiche une **« URL de l'application Web »** qui se termine
   par **`/exec`**. Cliquez **« Copier »** et **gardez cette adresse** avec votre
   phrase secrète.

✅ *Vous avez : l'adresse du facteur (…/exec) et votre phrase secrète. Ce sont
les deux seules choses dont le robot a besoin.*

---

## Étape 4 — Donner l'adresse et la phrase secrète au robot

*(Si une personne technique héberge le robot : envoyez-lui simplement ces deux
informations, elle fera cette étape, et vous passez directement à l'étape 6.)*

1. Dans votre dossier de travail, **double-cliquez sur `lancer_veille.bat`**. Une
   fenêtre noire s'ouvre et le programme s'installe tout seul (quelques minutes
   la première fois). **C'est normal.**
2. Au premier passage, il crée un fichier de réglages **`.env`** et s'arrête.
   **Ouvrez ce fichier `.env`** (clic droit → « Ouvrir avec » → **Bloc-notes**).
3. Complétez les deux lignes :

   ```
   APPSCRIPT_URL=collez-ici-l-adresse-qui-se-termine-par-/exec
   APPSCRIPT_TOKEN=votre-phrase-secrète
   ```

4. **Enregistrez** (Fichier → Enregistrer) et fermez le Bloc-notes.

✅ *Le robot sait maintenant à quel facteur remettre les données.*

---

## Étape 5 — Premier démarrage

1. **Une seule commande fait tout** : dans votre dossier, maintenez la
   touche **Maj**, faites un **clic droit** dans une zone vide → **« Ouvrir la
   fenêtre PowerShell ici »**, puis tapez :

   ```
   lancer_veille.bat init
   ```

   Le programme prépare le tableau (les onglets **Subventions**, **Journal** et
   **Archives** apparaissent, avec les couleurs), puis **enchaîne aussitôt la
   première collecte** : il visite les sites (quelques minutes) et remplit
   votre tableau. À la fin, il affiche `Veille terminée`.
2. **Ouvrez votre tableau Google Sheets** : il est rempli de subventions ! 🎉

Au premier démarrage, le programme s'est aussi **programmé lui-même** pour se
relancer **chaque matin à 7 h** (si l'ordinateur est allumé).

---

## Étape 6 — Au quotidien

- **Le matin**, la veille s'exécute seule et met le tableau à jour. Ouvrez
  simplement votre tableau pour voir les nouveautés (en **vert**, en haut).
- **Si l'ordinateur était éteint** à 7 h : **double-cliquez sur
  `lancer_veille.bat`** quand vous l'allumez. Aucun risque de doublon.
- **Pour vérifier que tout va bien** : l'onglet **Journal** du tableau liste
  chaque exécution. Tant que la colonne **alertes** est vide, tout fonctionne.
  Si un site a changé et n'est plus lu, une alerte y apparaît — signalez-la à
  la personne technique.

### Les couleurs du tableau

| Couleur | Signification |
|---|---|
| **Vert** | Subvention **nouvelle** (apparue à la dernière collecte) |
| **Orange** (colonne date limite) | Échéance dans **14 jours ou moins** — priorité |
| **Gris** | Programme **expiré** (date limite passée) |

---

## Étape 7 (facultative) — Brancher votre classeur personnel

Si vous tenez déjà **votre propre classeur** de subventions (celui avec vos
onglets « Grands programmes », « Tourisme », « Patrimoine »…), le robot peut y
**verser aussi ses trouvailles chaque matin**, chacune dans l'onglet de sa
catégorie — sans jamais abîmer votre travail :

- il **ajoute** ses lignes à la suite de vos onglets et ne touche **jamais** à
  vos lignes, à vos couleurs ni à l'onglet « Priorités » ;
- si **vous corrigez** une de ses lignes (montant, date, n'importe quoi), votre
  version **gagne** : il ne repassera pas dessus ;
- si vous **déplacez** une de ses lignes dans un autre onglet, il la suit et
  retient votre choix ;
- si vous **supprimez** une de ses lignes, elle ne reviendra pas ;
- vous pouvez trier, recolorer, renommer les onglets : rien ne casse.

**Mise en place** : refaites simplement l'étape 3 (le « facteur »), mais dans
**votre classeur** cette fois — même fichier `appscript/Code.gs`, votre phrase
secrète, déploiement en application Web — puis ajoutez dans le fichier `.env` :

```
CLASSEUR_APPSCRIPT_URL=l-adresse-/exec-de-CE-classeur
CLASSEUR_APPSCRIPT_TOKEN=la-phrase-secrète-de-CE-classeur
```

> **Une seule précaution** : tout à droite de ses lignes (colonne AI), le robot
> note un petit code du genre `rbt:a1b2c3…` — c'est sa **mémoire**. Laissez
> cette petite étiquette tranquille ; tout le reste est à vous.

*(Ligne supprimée par erreur ? La personne technique peut la faire revenir avec
`python -m veille.classeur --reactiver <code>`.)*

---

## En cas de problème

| Ce que vous voyez | Que faire |
|---|---|
| « Ni APPSCRIPT_URL ni SHEET_ID dans le fichier .env » | Le fichier `.env` n'est pas rempli. Reprenez l'étape 4. |
| « jeton invalide » | La phrase secrète du `.env` (APPSCRIPT_TOKEN) n'est pas **exactement** celle du script (étape 3b). Corrigez l'une ou l'autre. |
| « le JETON du script n'a pas été personnalisé » | Vous avez laissé `CHANGEZ-MOI` dans le script. Reprenez l'étape 3b, puis **redéployez** (Déployer → Gérer les déploiements → ✏️ → Version : Nouvelle version → Déployer). |
| « n'a pas répondu en JSON » | Le déploiement n'est pas en accès « Tout le monde », ou l'adresse copiée n'est pas celle en `/exec`. Reprenez l'étape 3c. |
| Le tableau reste vide après l'exécution | Vérifiez l'adresse `/exec` et la phrase secrète dans `.env` ; regardez l'onglet Journal. |
| « Python introuvable » puis blocage | Fermez la fenêtre et **relancez** `lancer_veille.bat` : Python vient d'être installé et sera visible au 2ᵉ lancement. |
| Ça ne s'exécute pas à 7 h | L'ordinateur doit être **allumé et la session ouverte**. Sinon, double-cliquez sur le script dans la journée — ou demandez un hébergement sur serveur (voir README). |

> **Vous modifiez le script plus tard ?** Après tout changement dans l'éditeur
> Apps Script, il faut **redéployer** : Déployer → **Gérer les déploiements** →
> ✏️ (modifier) → Version : **Nouvelle version** → Déployer. L'adresse `/exec`
> reste la même.

---

## Petit lexique

- **Google Sheets** : un tableur en ligne (comme Excel), gratuit, dans votre
  navigateur.
- **Apps Script** : le langage de « macros » de Google Sheets. Notre
  script-facteur est écrit avec ça et vit à l'intérieur de votre tableau.
- **Déployer** : mettre le script-facteur en service, avec une adresse web à lui.
- **Phrase secrète (jeton)** : le mot de passe convenu entre le robot et le
  facteur. Sans elle, personne ne peut écrire dans votre tableau.
- **`.env`** : le petit fichier de réglages où l'on donne au robot l'adresse du
  facteur et la phrase secrète.

---

*Détails techniques (structure du code, ajout/réparation de sources, exécution
sur serveur Linux/cPanel, option « compte de service ») : voir
[README.md](README.md).*
