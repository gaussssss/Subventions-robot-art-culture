/**
 * Veille des subventions — passerelle Google Apps Script.
 *
 * Ce script se colle DANS le Google Sheet (Extensions → Apps Script) et se
 * déploie en « application Web ». Le robot Python lui envoie les données par
 * HTTP ; c'est le script, qui appartient au propriétaire de la feuille, qui
 * écrit dedans. Avantage : AUCUN compte de service ni clé JSON à créer.
 *
 * Mise en place (une seule fois) — détail pas à pas dans GUIDE.md :
 *   1. Ouvrir la feuille → Extensions → Apps Script, remplacer le contenu
 *      par ce fichier.
 *   2. Remplacer le JETON ci-dessous par une phrase secrète de votre choix.
 *   3. Déployer → Nouveau déploiement → type « Application Web » →
 *      Exécuter en tant que : Moi ; Accès : Tout le monde → Déployer.
 *   4. Copier l'URL qui se termine par /exec dans le fichier .env du robot
 *      (APPSCRIPT_URL=...) avec la même phrase secrète (APPSCRIPT_TOKEN=...).
 *
 * Sécurité : l'URL n'accepte que les requêtes portant le bon jeton ; le
 * script ne touche qu'à la feuille à laquelle il est rattaché.
 */

const JETON = "CHANGEZ-MOI"; // ← remplacez par votre phrase secrète

const ONGLET_SUBVENTIONS = "Subventions";
const ONGLET_JOURNAL = "Journal";
const ONGLET_ARCHIVES = "Archives";

const COLONNES = [
  "nom_programme", "organisme", "palier", "discipline", "type", "montant",
  "date_limite", "admissibilite_obnl", "url", "statut", "date_detection",
  "derniere_verification", "notes_agent", "id_unique",
];
const COLONNES_JOURNAL = [
  "date", "sources_visitées", "sources_en_erreur", "nouveautés_détectées",
  "programmes_expirés", "coût_api_estimé", "durée_exécution", "alertes",
];
const COLONNES_ARCHIVES = COLONNES.concat(["date_archivage"]);

/** Point d'entrée : le robot envoie {jeton, action, ...} en JSON. */
function doPost(e) {
  let corps;
  try {
    corps = JSON.parse(e.postData.contents);
  } catch (err) {
    return _reponse({ ok: false, erreur: "corps illisible (JSON attendu)" });
  }
  if (!corps || corps.jeton !== JETON) {
    return _reponse({ ok: false, erreur: "jeton invalide" });
  }
  if (JETON === "CHANGEZ-MOI") {
    return _reponse({ ok: false, erreur: "le JETON du script n'a pas été personnalisé" });
  }

  // Une exécution à la fois : évite qu'une collecte manuelle et la collecte
  // planifiée s'écrivent dessus.
  const verrou = LockService.getScriptLock();
  verrou.waitLock(120 * 1000);
  try {
    switch (corps.action) {
      case "ping":       return _reponse({ ok: true, reponse: "pong" });
      case "structure":  return _reponse(_structure());
      case "init":       return _reponse(_init());
      case "lire":       return _reponse(_lire());
      case "ecrire":     return _reponse(_ecrire(corps.lignes || []));
      case "archiver":   return _reponse(_archiver(corps.lignes || []));
      case "journal":    return _reponse(_journal(corps.ligne || []));
      // Actions « classeur » : utilisées quand ce script est collé dans le
      // classeur manuel (2e feuille, organisée par onglets de catégories).
      // Elles n'écrivent QUE des valeurs — jamais de couleur ni de mise en
      // forme : les codes couleurs manuels restent intacts.
      case "classeur_lire":    return _reponse(_classeurLire());
      case "classeur_ajouter": return _reponse(_classeurAjouter(corps.gid, corps.lignes || []));
      case "classeur_maj":     return _reponse(_classeurMaj(corps.gid, corps.cellules || []));
      case "classeur_reinitialiser": return _reponse(_classeurReinitialiser(corps.gids || [], corps.entetes || []));
      default:           return _reponse({ ok: false, erreur: "action inconnue : " + corps.action });
    }
  } catch (err) {
    return _reponse({ ok: false, erreur: String(err) });
  } finally {
    verrou.releaseLock();
  }
}

/** Visite dans un navigateur : permet de vérifier que le déploiement répond. */
function doGet() {
  return _reponse({ ok: true, reponse: "Veille des subventions — passerelle active. Le robot utilise POST." });
}

function _reponse(objet) {
  return ContentService.createTextOutput(JSON.stringify(objet))
    .setMimeType(ContentService.MimeType.JSON);
}

function _classeur() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

/** Crée les onglets et les en-têtes manquants (ré-exécutable sans danger). */
function _structure() {
  const attendus = [
    [ONGLET_SUBVENTIONS, COLONNES],
    [ONGLET_JOURNAL, COLONNES_JOURNAL],
    [ONGLET_ARCHIVES, COLONNES_ARCHIVES],
  ];
  const classeur = _classeur();
  attendus.forEach(function (paire) {
    const titre = paire[0], colonnes = paire[1];
    let onglet = classeur.getSheetByName(titre);
    if (!onglet) onglet = classeur.insertSheet(titre);
    const premiere = onglet.getRange(1, 1, 1, colonnes.length).getValues()[0];
    if (!premiere.join("")) {
      onglet.getRange(1, 1, 1, colonnes.length).setValues([colonnes]);
    }
  });
  return { ok: true };
}

/** Initialisation complète : structure + gras/gel + mise en forme conditionnelle. */
function _init() {
  _structure();
  const onglet = _classeur().getSheetByName(ONGLET_SUBVENTIONS);
  onglet.getRange(1, 1, 1, COLONNES.length).setFontWeight("bold");
  onglet.setFrozenRows(1);

  const NB_LIGNES = 5000;
  const colDate = COLONNES.indexOf("date_limite") + 1;    // G
  const colStatut = COLONNES.indexOf("statut") + 1;       // J
  const lettreDate = String.fromCharCode(64 + colDate);
  const lettreStatut = String.fromCharCode(64 + colStatut);

  const plageTableau = onglet.getRange(2, 1, NB_LIGNES - 1, COLONNES.length);
  const plageDates = onglet.getRange(2, colDate, NB_LIGNES - 1, 1);

  // L'ordre compte (première règle gagnante par cellule) :
  // 1. échéance ≤ 14 jours en orange ; 2. « Nouveau » en vert ; 3. « Expiré » en gris.
  const regles = [
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied(
        '=IFERROR(AND($' + lettreDate + '2<>"", $' + lettreDate + '2<>"continu", ' +
        'DATEVALUE($' + lettreDate + '2)>=TODAY(), ' +
        'DATEVALUE($' + lettreDate + '2)-TODAY()<=14), FALSE)')
      .setBackground("#FDE5CC").setRanges([plageDates]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=$' + lettreStatut + '2="Nouveau"')
      .setBackground("#D9EFD3").setRanges([plageTableau]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=$' + lettreStatut + '2="Expiré"')
      .setBackground("#F0F0F0").setRanges([plageTableau]).build(),
  ];
  onglet.setConditionalFormatRules(regles); // remplace les règles existantes (idempotent)
  return { ok: true, reponse: "feuille initialisée" };
}

/** Renvoie toutes les lignes de Subventions (sans l'en-tête). */
function _lire() {
  const onglet = _classeur().getSheetByName(ONGLET_SUBVENTIONS);
  if (!onglet) return { ok: true, lignes: [] };
  const derniere = onglet.getLastRow();
  if (derniere < 2) return { ok: true, lignes: [] };
  const valeurs = onglet
    .getRange(2, 1, derniere - 1, COLONNES.length)
    .getDisplayValues(); // texte tel qu'affiché : les dates restent AAAA-MM-JJ
  return { ok: true, lignes: valeurs };
}

/** Réécrit le tableau en un seul lot, puis efface les lignes devenues orphelines. */
function _ecrire(lignes) {
  const onglet = _classeur().getSheetByName(ONGLET_SUBVENTIONS);
  const anciennes = Math.max(onglet.getLastRow() - 1, 0);
  if (lignes.length) {
    const normalisees = lignes.map(function (l) {
      const rangee = l.slice(0, COLONNES.length);
      while (rangee.length < COLONNES.length) rangee.push("");
      return rangee.map(String);
    });
    onglet.getRange(2, 1, normalisees.length, COLONNES.length)
      .setNumberFormat("@") // texte brut : ne pas laisser Sheets réinterpréter les dates
      .setValues(normalisees);
  }
  if (anciennes > lignes.length) {
    onglet.getRange(lignes.length + 2, 1, anciennes - lignes.length, COLONNES.length)
      .clearContent();
  }
  return { ok: true, reponse: lignes.length + " ligne(s) écrites" };
}

/** Ajoute des lignes expirées à l'onglet Archives. */
function _archiver(lignes) {
  if (!lignes.length) return { ok: true, reponse: "rien à archiver" };
  const onglet = _classeur().getSheetByName(ONGLET_ARCHIVES);
  const debut = onglet.getLastRow() + 1;
  const normalisees = lignes.map(function (l) {
    const rangee = l.slice(0, COLONNES_ARCHIVES.length);
    while (rangee.length < COLONNES_ARCHIVES.length) rangee.push("");
    return rangee.map(String);
  });
  onglet.getRange(debut, 1, normalisees.length, COLONNES_ARCHIVES.length)
    .setNumberFormat("@")
    .setValues(normalisees);
  return { ok: true, reponse: lignes.length + " ligne(s) archivées" };
}

/** Ajoute une ligne au Journal. */
function _journal(ligne) {
  const onglet = _classeur().getSheetByName(ONGLET_JOURNAL);
  onglet.appendRow(ligne.map(String));
  return { ok: true };
}

// ─── Actions « classeur manuel » ─────────────────────────────────────────────
// Le robot suit les onglets par leur identifiant interne (gid), stable même si
// l'onglet est renommé ou déplacé.

function _ongletParGid(gid) {
  const onglets = _classeur().getSheets();
  for (let i = 0; i < onglets.length; i++) {
    if (onglets[i].getSheetId() === gid) return onglets[i];
  }
  return null;
}

/** Renvoie tous les onglets (gid, nom) avec leurs valeurs affichées. */
function _classeurLire() {
  const onglets = _classeur().getSheets().map(function (o) {
    const nbLignes = o.getLastRow(), nbColonnes = o.getLastColumn();
    return {
      gid: o.getSheetId(),
      nom: o.getName(),
      valeurs: (nbLignes && nbColonnes)
        ? o.getRange(1, 1, nbLignes, nbColonnes).getDisplayValues()
        : [],
    };
  });
  return { ok: true, onglets: onglets };
}

/** Ajoute des lignes à la suite d'un onglet (valeurs texte uniquement). */
function _classeurAjouter(gid, lignes) {
  const onglet = _ongletParGid(gid);
  if (!onglet) return { ok: false, erreur: "onglet introuvable (gid " + gid + ")" };
  if (!lignes.length) return { ok: true, reponse: "rien à ajouter" };
  const largeur = Math.max.apply(null, lignes.map(function (l) { return l.length; }));
  const normalisees = lignes.map(function (l) {
    const rangee = l.slice();
    while (rangee.length < largeur) rangee.push("");
    return rangee.map(String);
  });
  const plage = onglet.getRange(onglet.getLastRow() + 1, 1, normalisees.length, largeur);
  // Retirer toute règle de validation (liste déroulante) HÉRITÉE sur les lignes
  // que le robot ajoute : sinon Sheets rejette une valeur hors liste — ex.
  // « Voir critères » dans une colonne « Pour qui » à choix imposé. Ne touche
  // qu'aux lignes du robot ; les listes déroulantes des lignes de l'utilisateur
  // restent intactes.
  plage.clearDataValidations();
  plage.setNumberFormat("@") // texte brut : ne pas laisser Sheets réinterpréter les dates
    .setValues(normalisees);
  return { ok: true, reponse: normalisees.length + " ligne(s) ajoutée(s)" };
}

/**
 * Repart à neuf pour une liste d'onglets : efface tout leur contenu et pose la
 * ligne d'en-têtes fournie (le schéma à 14 colonnes du robot). Utilisé une seule
 * fois pour aligner le classeur sur la structure du Sheet du robot. NE TOUCHE
 * QU'AUX onglets dont le gid est fourni — les autres (Priorités, etc.) sont
 * intacts. Faire une copie du classeur avant : cette action efface les données.
 */
function _classeurReinitialiser(gids, entetes) {
  const faits = [];
  gids.forEach(function (gid) {
    const onglet = _ongletParGid(gid);
    if (!onglet) return;
    // Tout enlever pour repartir vraiment propre. onglet.clear() ne suffit pas :
    // il laisse la mise en forme conditionnelle, les couleurs en alternance
    // (bandes) et les listes déroulantes posées sur des colonnes entières.
    const tout = onglet.getRange(1, 1, onglet.getMaxRows(), onglet.getMaxColumns());
    tout.clearContent();          // valeurs
    tout.clearFormat();           // couleurs de fond, polices, bordures…
    tout.clearDataValidations();  // listes déroulantes
    tout.clearNote();             // commentaires
    onglet.clearConditionalFormatRules();                 // couleurs pilotées par règles
    onglet.getBandings().forEach(function (b) { b.remove(); }); // couleurs en alternance
    if (onglet.getFrozenRows()) onglet.setFrozenRows(0);
    if (onglet.getFrozenColumns()) onglet.setFrozenColumns(0);
    if (entetes.length) {
      onglet.getRange(1, 1, 1, entetes.length)
        .setValues([entetes.map(String)])
        .setFontWeight("bold");
      onglet.setFrozenRows(1);
    }
    faits.push(onglet.getName());
  });
  return { ok: true, reponse: faits.length + " onglet(s) réinitialisé(s) : " + faits.join(", ") };
}

/** Met à jour des cellules précises {ligne, colonne, valeur} (valeurs uniquement). */
function _classeurMaj(gid, cellules) {
  const onglet = _ongletParGid(gid);
  if (!onglet) return { ok: false, erreur: "onglet introuvable (gid " + gid + ")" };
  cellules.forEach(function (c) {
    const cellule = onglet.getRange(c.ligne, c.colonne);
    cellule.clearDataValidations(); // idem : ne pas buter sur une liste imposée
    cellule.setNumberFormat("@").setValue(String(c.valeur));
  });
  return { ok: true, reponse: cellules.length + " cellule(s) mise(s) à jour" };
}
