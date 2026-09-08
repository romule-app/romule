"""Every sentence the server shows, in one place.

Why they left the code
----------------------
They were written at the call site, in thirty files. Two things followed from
that, and both were reported by someone using Romule rather than reading it:

  * the French had no accents. « Range », « recuperee », « termine » — that is
    what the log showed. Nothing required it: the container writes UTF-8
    without blinking, and `console.py` now reconfigures the terminal so a host
    running under `LANG=C` cannot break a line either;
  * changing any of it meant a sweep of thirty files, so nobody did.

Here they are named, accented, and read once.

The French text is still the KEY of the translation catalogue — that is the
project's i18n mechanism, not a style — so `fr.json` and `en.json` carry the
same sentences. What changed is that the code no longer spells them out.

`verifier-journal.py` reads THIS file: a constant that is not in the catalogue
is an error, and this is the one place to look.

The `V1_` constants are the public API's answers. They are English by contract
and are NOT translated: every client written against `/api/v1` reads them.
"""

# --------------------------------------------- what Romule says
ACCES_DEJA_DEFINI = 'Cette installation a déjà un accès défini.'
ACCES_JETON_RAPPEL = (
    'Accès protégé par un jeton. `romule token show` le rappelle.')
ACCES_JETON_REQUIS = 'Accès protégé : jeton requis.'
ACCES_NON_CHOISI = (
    "PERSONNE N'A ENCORE CHOISI COMMENT PROTÉGER CET ACCÈS : tout appareil pouvant joindre cette adresse a tous les droits.")
ACCES_OUVERT = 'Accessible SANS MOT DE PASSE par tout appareil du réseau.'
ACTIVE_ACCES_RESEAU = "Active d'abord l'accès réseau (Réglages)."
ADB_ABSENT = 'adb absent — la console ne pourra pas être pilotée'
ADB_INTROUVABLE = 'adb introuvable'
ADRESSE_HOTE_CONTENEUR = (
    '  (adresse valable depuis la machine qui héberge le conteneur ; déclare ROMULE_PUBLIC_HOST pour les autres)')
ADRESSE_OUVRE_ASSISTANT = (
    "Ouvre %s et réponds à l'étape « Ton accès » de l'assistant.")
ADRESSE_MANQUANTE = 'adresse manquante'
ADRESSE_OU_CODE_MANQUANT = 'adresse ou code manquant'
ANALYSE_INTERROMPUE = 'Analyse interrompue.'
ARBORESCENCE_CREEE = (
    "Création de l'arborescence GAMES/UPDATE/DLC sur la console.")
ARCHIVE_SANS_JEU = '  Aucun jeu dedans (données non installables) → corbeille.'
ARCHIVE_SANS_OUTIL = (
    '  Aucun outil pour cette archive (installe The Unarchiver : brew install unar).')
ARRET_DEMANDE = 'Arrêt demandé, fermeture…'
AUCUN_COMPTE_CONNECTE = 'Aucun compte connecté.'
AUCUN_TRANSFERT = 'Aucun transfert à reprendre.'
AUTH_ACTIVEE = 'Authentification activée : ce navigateur reste connecté.'
AUTH_DESACTIVEE_OUVRE = (
    "Authentification désactivée : l'accès réseau est ouvert SANS MOT DE PASSE, sinon plus personne n'entrerait.")
BRANCHE_EN_USB = (
    'Branche le handheld en USB, autorise le débogage, puis réessaie.')
CHEMIN_HORS_BASES = 'chemin hors des dossiers autorisés'
CLES_RIEN_DE_NEUF = 'Clés de titre : rien de nouveau.'
CODE_INCORRECT = "Code incorrect. Vérifie l'heure de ton téléphone."
COMPTE_ADRESSE_INCONNUE = 'Aucun compte avec cette adresse.'
COMPTE_INTROUVABLE = 'Compte introuvable.'
COMPTE_SUPPRIME = 'Compte supprimé.'
CONNECTE_LA_CONSOLE = "Connecte d'abord la console."
CONNEXION_INTERNE_OFF = 'connexion interne désactivée'
CONSOLE_A_JOUR = 'Console à jour.'
CONSOLE_NON_CONNECTEE = 'Console non connectée.'
CONTENU_INATTENDU = 'contenu inattendu'
DERNIER_ADMIN = (
    "C'est le dernier administrateur : promeus quelqu'un d'autre avant de le supprimer.")
DERNIER_COMPTE = (
    "C'est le dernier compte : il doit rester quelqu'un pour se connecter.")
DOSSIER_CIBLE_INCONNU = 'Dossier cible inconnu sur la console.'
DOSSIER_ILLISIBLE = 'lecture refusée sur ce dossier'
DOSSIER_INEXISTANT = "ce dossier n'existe pas"
EDEN_CONFIG_CREEE = 'Aucune configuration pour ce jeu : création.'
EDEN_CONFIG_RETIREE = (
    "Configuration du jeu retirée (retour à l'état d'origine).")
EDEN_CONTENU_INVALIDE = 'Contenu invalide : aucune section reconnue.'
EDEN_GLOBALE_ABSENTE = 'Configuration globale introuvable sur la console.'
EDEN_JEU_REQUIS = 'Un jeu doit être précisé.'
EDEN_SAUVEGARDE = 'Ancienne version conservée dans _eden-backup/.'
EDEN_SAUVEGARDE_ABSENTE = 'Sauvegarde introuvable pour ce jeu.'
EDEN_SAUVEGARDE_NON_PRECISEE = 'Sauvegarde non précisée.'
EMAIL_DEJA_PRIS = 'Un compte existe déjà avec cette adresse.'
EMAIL_INVALIDE = 'Adresse email invalide.'
ER_CACHE_VIDE = 'Cache EmuReady vide.'
ER_SANS_CONFIG = 'ce rapport ne fournit pas de configuration Eden'
FICHES_SWITCH_EN_CACHE = 'Fiches Switch : toutes déjà en cache.'
FICHIER_INCOMPLET = (
    "Un fichier incomplet apparaît dans Eden comme un jeu qui ne démarre pas. Retélécharge-le, puis relance l'envoi.")
FICHIER_VIDE = 'fichier vide ou tronqué'
IDENTIFIANTS_INCORRECTS = 'Email ou mot de passe incorrect.'
IGDB_IDENTIFIANTS_REQUIS = (
    'Client ID et Client Secret Twitch sont nécessaires.')
IGDB_REFUSE = 'Twitch a refusé ces identifiants.'
IMAGE_INCONNUE = "Format d'image non reconnu (PNG, JPEG, GIF ou WebP)."
IMPORT_VIDE = (
    'Aucun jeu à ranger dans _import (archives non extraites éventuellement laissées).')
INSTALL_INTERROMPUE = 'Installation interrompue.'
JOURNAL_EFFACE = 'Journal effacé.'
LANGUE_INCONNUE = 'langue inconnue'
LOT_INTROUVABLE = 'Lot introuvable.'
LOT_INVALIDE = 'Lot invalide.'
MDP_ACTUEL_INCORRECT = 'Mot de passe actuel incorrect.'
MDP_CHANGE = 'Mot de passe changé. Les autres appareils ont été déconnectés.'
MDP_CONTIENT_EMAIL = 'Le mot de passe ne doit pas contenir ton adresse email.'
MDP_COURANT = (
    'Ce mot de passe figure parmi les plus utilisés : choisis-en un autre.')
MDP_INCHANGE = "Le nouveau mot de passe est identique à l'ancien."
MDP_INCORRECT = 'Mot de passe incorrect.'
MDP_REPETITIF = 'Ce mot de passe est trop répétitif.'
NAND_AUTO_REPORTEE = (
    'Activation automatique : console non connectée, reportée.')
OIDC_COMPTE_REFUSE = (
    "Ce compte n'est pas autorisé à accéder à cette ludothèque.")
OIDC_EMETTEUR = 'Émetteur du jeton inattendu.'
OIDC_JETON_EXPIRE = 'Jeton expiré.'
OIDC_JETON_FUTUR = "Jeton daté du futur : vérifie l'horloge du serveur."
OIDC_JETON_ILLISIBLE = "Jeton d'identité illisible."
OIDC_MAUVAISE_AUDIENCE = 'Ce jeton ne nous est pas destiné.'
OIDC_NONCE = 'Nonce inattendu : la réponse ne correspond pas à la demande.'
OIDC_REDIRECT = "L'adresse de retour ne correspond pas à la demande."
OIDC_SANS_CODE = "Aucun code d'autorisation dans la réponse."
OIDC_SANS_FOURNISSEUR = 'Aucune adresse de fournisseur configurée.'
OIDC_SANS_JETON = "Le fournisseur n'a pas renvoyé de jeton d'identité."
OIDC_SANS_JWKS = 'Le fournisseur ne publie pas ses clés (jwks_uri).'
OIDC_SIGNATURE = "Signature du jeton d'identité invalide."
OIDC_STATE = 'Réponse inattendue (state) : connexion abandonnée.'
OIDC_TRANSIT_INCONNU = 'Demande de connexion expirée ou inconnue. Recommence.'
ORIGINE_INATTENDUE = 'origine inattendue'
PAS_UN_NSP = "ce fichier n'est pas une archive NSP (PFS0)"
PHOTO_MISE_A_JOUR = 'Photo mise à jour.'
PHOTO_RETIREE = 'Photo retirée.'
PLATEFORME_AUTRE_NOM = (
    "Si l'une d'elles existe sous un autre nom, ouvre sa fiche dans les Réglages et indique son dossier.")
PROFIL_ENREGISTRE = 'Profil enregistré.'
RANGEMENT_SANS_CONSOLE = (
    "Rien n'a été rangé : la console n'est pas connectée. Branche-la, ou connecte-la sans fil, puis relance.")
RAPPORT_SANS_CONFIG = 'Ce rapport ne contient aucune configuration.'
REBRANCHE_LA = 'Rebranche-la : la reprise ne renverra que ce qui manque.'
RELANCE_EDEN = (
    'Relance Eden pour que les mises à jour et DLC soient pris en compte.')
REPRISE_ABANDONNEE = 'Reprise abandonnée.'
REPRISE_PROPOSEE = 'La reprise est proposée au prochain envoi.'
REQUETE_INVALIDE = 'requête invalide'
RESERVE_ADMIN = "Réservé à l'administrateur."
RIEN_A_CONVERTIR = 'Rien à convertir.'
RIEN_A_ENVOYER = 'Rien à envoyer.'
RIEN_A_ENVOYER_A_JOUR = 'Rien à envoyer : la console est déjà à jour.'
RIEN_A_VERIFIER = 'Aucun fichier à vérifier.'
RIEN_RECUPERE = 'Rien de récupéré depuis la console.'
RIEN_SAUVEGARDE = "Rien n'a pu être sauvegardé."
ROMS_ROOT_ABSENTE = "Aucune racine de ROMs définie : renseigne-la d'abord."
ROUTE_JETON_INCONNUE = 'route inconnue : /auth/jeton'
SANS_FOURNISSEUR_JAQUETTES = (
    'Sans clé SteamGridDB ni identifiants IGDB, les jeux des autres plateformes gardent le nom de leur fichier.')
SAUVEGARDES_ABSENTES = 'Aucun dossier de sauvegardes trouvé sur la console.'
SAUVEGARDES_CHEMIN = 'Indique son chemin dans les Réglages si tu le connais.'
SAUVEGARDE_ENREGISTREE = 'Sauvegarde enregistrée.'
SAUVEGARDE_INTERROMPUE = 'Sauvegarde interrompue.'
SECURITE_OK = "Sécurité : aucun point d'attention."
SGDB_CLE_REFUSEE = 'Clé refusée par SteamGridDB.'
SGDB_SANS_CLE = 'Aucune clé renseignée.'
SYNC_INTERROMPUE = 'Synchronisation interrompue.'
TACHE_EN_COURS = 'Une tâche est déjà en cours.'
TOTP_ACTIVEE = 'Double authentification activée.'
TOTP_RETIREE = 'Double authentification retirée.'
TOTP_SANS_SECRET = 'Commence par générer un secret.'
TRAVAIL_EN_COURS = 'un travail est en cours — réessaie après'
UN_ADMIN_MINIMUM = 'Il doit rester au moins un administrateur.'
VERIF_INTERROMPUE = 'Vérification interrompue.'
WIFI_OUBLIE = 'Connexion sans fil oubliée.'


# ------------------------------------------ the /api/v1 contract
# English, and NOT translated: clients are written against them.
V1_ADRESSE_REQUISE = 'An address is required.'
V1_CONSOLE_INCONNUE = 'Unknown console.'
V1_DERNIERE_CONSOLE = 'The last console cannot be removed.'
V1_DESTINATION_INCONNUE = 'Unknown destination.'
V1_GESTE_INCONNU = 'Unknown gesture.'
V1_JEU_INCONNU = 'No game with that key.'
V1_Q_REQUIS = 'q is required.'
V1_REQUETE_REFUSEE = 'The request could not be served.'
V1_ROUTE_INCONNUE = 'Unknown route. See /api/v1/openapi.json.'
V1_TACHE_EN_COURS = 'Another task is already running.'
V1_TACHE_INCONNUE = 'Unknown task.'


# ------------------------------------------- the startup banner
# The LABELS. Translated before the column is measured, so the banner stays
# aligned in either language.
B_VERSION = 'Version'
B_INTERFACE = 'Interface'
B_RESEAU = 'Réseau'
B_ACCES = 'Accès'
B_COMPTES = 'Comptes'
B_LUDO = 'Ludothèque'
B_DONNEES = 'Données'
B_DEPOT = 'Dépôt'
B_JOURNAL = 'Journal'
B_OUTILS = 'Outils'
B_JAQUETTES = 'Jaquettes'
B_JOURNALISATION = 'Journalisation'

# The VALUES. Templates, never the interpolated result: the catalogue cannot
# hold a sentence that only exists once the path is known.
B_VERSION_VAL = '%s   Python %s sur %s'
B_INTERFACE_VAL = '%s   (Ctrl+C pour arrêter)'
B_RESEAU_LOCAL = ('cette machine seulement — ROMULE_BIND=0.0.0.0, '
                  'ROMULE_LAN=1 ou un jeton, puis redémarrer')
B_RESEAU_PUBLIE = '%s   (téléphone, console, tablette)'
B_RESEAU_SANS_HOTE = ('port %s publié — déclare ROMULE_PUBLIC_HOST pour que '
                      "Romule sache sous quelle adresse on l'atteint")
B_ACCES_AUCUNE = 'aucune'
B_ACCES_INTERNE = 'comptes internes'
B_ACCES_JETON = ' + jeton'
B_ACCES_JETON_ENGENDRE = ' + jeton engendré'
B_LUDO_IMPOSEE = 'imposée par ROMULE_LIBRARY'
B_LUDO_MODIFIABLE = "modifiable depuis l'interface"
B_DONNEES_VAL = '%s   (configuration, comptes, jaquettes)'
B_DEPOT_VAL = '%s   (glisse tes fichiers ici)'
B_OUTILS_AUCUN = 'aucun — conversion et console indisponibles'


# ------------------------------------------- what a task says while it runs
A_ACTIVATION_AUTO = "Activation automatique de %d mise(s) à jour / DLC dans l'émulateur."
A_ANALYSE_DE = 'Analyse de %s (%d plateforme(s) connues).'
A_ARCHIVE_ILLISIBLE = '  Archive illisible : %s'
A_AUCUNE_FICHE = 'Aucune fiche trouvée : %s'
A_AUTRES_COMPLETES = 'Fiches des autres plateformes : les %d sont complètes.'
A_AUTRES_RECHERCHE = '%d jeu(x) sur les autres plateformes : recherche du titre%s…'
A_CLASSES_MAIN = '%d fichier(s) classé(s) à la main.'
A_CONF_INDISPO = 'Configuration indisponible : %s'
A_CONF_INDISPO_DE = '  %s : configuration indisponible (%s)'
A_CONF_RECUP = 'Configuration récupérée (%d octets).'
A_CONVERSION_IMPORTES = 'Conversion des %d fichier(s) importé(s)…'
A_DECOMPRESSION = 'Décompression de %s…'
A_DEJA_IGNORE = 'Déjà présent, ignoré : %s'
A_DEJA_PRESENT = 'Déjà présent : %s'
A_DEPOT_AMBIGU = "%s reste dans le dépôt : l'extension %s est partagée par %s. Range-le dans le dossier voulu."
A_DEPOT_INCONNU = '%s reste dans le dépôt : aucune plateforme ne reconnaît %s.'
A_ECHEC = 'Échec (%s) : %s'
A_ELEMENTS_EXTRAITS = '  %d élément(s) extrait(s).'
A_EMUREADY = "Consultation d'EmuReady pour %d jeu(x)…"
A_ETAPE1_COPIE = 'Étape 1/%d — copie de %d fichier(s) vers la console.'
A_ETAPE1_RIEN = 'Étape 1/%d — aucun fichier à copier.'
A_ETAPE2_ACTIVATION = "Étape 2/%d — activation de %d mise(s) à jour / DLC dans l'émulateur."
A_ETAPE2_RIEN = 'Étape 2/%d — rien à activer.'
A_ETAPE3_REGLAGES = 'Étape 3/%d — réglages recommandés pour %d jeu(x).'
A_EXTRACTION_KO = '  Extraction impossible : %s'
A_FICHES_INTERROMPUES = 'Fiches interrompues (%d/%d).'
A_FICHES_RECHERCHE = 'Recherche des fiches de %d nouveau(x) jeu(x)…'
A_FICHES_RECUP = '%d fiche(s) récupérée(s) sur %d.'
A_FICHES_SWITCH = 'Récupération de %d fiche(s) Switch en %s…'
A_FICHES_SWITCH_BILAN = '%d fiche(s) Switch récupérée(s) sur %d.'
A_FICHE_INDISPO = 'Fiche indisponible pour %s : %s'
A_HORS_DEPOT = 'Ignoré (hors du dépôt) : %s'
A_IMPORT_TERMINE = 'Import terminé (%d fichier(s)).'
A_INTERROMPU = 'Interrompu (%d/%d).'
A_INTERROMPU_FICHES = 'Interrompu : %d fiche(s) traitée(s) sur %d.'
A_LIGNE_PLATEFORME = '  %-20s %4d jeu(x)  %s'
A_PLATEFORMES_BILAN = '%d plateforme(s) avec des jeux, %d jeu(x) au total.'
A_PLATEFORME_INCONNUE = 'Plateforme inconnue pour %s : %s'
A_PROFIL_APPLIQUE = 'Application du profil « %s »…'
A_PROFIL_INTROUVABLE = 'Profil introuvable : %s'
A_RANGE = 'Rangé : %s → %s/'
A_RANGEMENT_KO = 'Impossible de ranger %s : %s'
A_RANGES_DANS = '%d fichier(s) rangé(s) dans %s.'
A_RANGES_GUD = '%d fichier(s) rangé(s) en GAMES / UPDATE / DLC.'
A_RAPPORT_SANS_CONF = '  %s : rapport sans configuration.'
A_REGLAGES_PARTIELS = "Terminé, mais %d réglage(s) sur %d n'ont pas pu être appliqués."
A_SANS_RESUME = '%d jeu(x) sans résumé : IGDB ne les connaît pas sous ce nom.'
A_TITRES_BILAN = '%d titre(s) sur %d, dont %d avec un résumé (%d en %s).'
A_VERIF = 'Vérification de %d fichier(s)%s…'


# --------------------------- what the console, the transfers and the server say
C_CONVERSION = 'Conversion : %s'
C_CONVERSION_FINIE = 'Conversion terminée (%d/%d).'
C_ECHEC = 'ÉCHEC %s : %s'
C_EXCLU = 'EXCLU %s : exige master_key_%d, tu as %d'
C_MASTER_KEYS = 'Contrôle des master keys (%d fichier(s))…'
C_OK_MO = 'OK  %s (%.1f Mo)'
D_AUCUN_APPAREIL = 'Aucun appareil adb prêt (état : %s).'
D_DECONNECTEE = 'Console déconnectée — transfert arrêté (%d/%d envoyés).'
D_DEJA_CONSOLE = '%d fichier(s) déjà sur la console, ignoré(s).'
D_ECHEC = '  ÉCHEC : %s'
D_ECHEC_FINAL = '  ÉCHEC définitif : %s'
D_ECHEC_RETRY = '  échec (%s) — nouvelle tentative…'
D_ECHEC_SUPPR = 'Échec de la suppression : %s'
D_ENVOI = 'Envoi : %s'
D_ENVOI_VERS = 'Envoi : %s  →  %s/'
D_IDENTIQUES = "%d fichier(s) déjà présents à l'identique, ignoré(s)."
D_INTERROMPU = 'Transfert interrompu (%d/%d).'
D_INTERROMPU_ENVOYES = 'Transfert interrompu (%d/%d envoyés).'
D_OK = 'OK  %s'
D_RANGE = 'Rangé : %s → %s/'
D_RECUPERATION = 'Récupération : %s'
D_RECUP_INTERROMPUE = 'Récupération interrompue (%d fichier(s) reçu(s)).'
D_RECU_MO = '  reçu (%.1f Mo)'
D_REFUSE_INCOMPLET = 'Refusé : %s est incomplet — %s'
D_SUPPRIME = 'Supprimé : %s'
D_SUPPRIMES = '%d fichier(s) supprimé(s) de la console.'
D_TERMINE = 'Transfert terminé (%d/%d) vers %s.'
EM_COMPAT = 'Compatibilité mise à jour pour %d jeu(x).'
E_APPLIQUES = '%d réglage(s) appliqué(s) %s.'
E_CONF_APPLIQUEE = 'Configuration appliquée : %d section(s), %d réglage(s) spécifique(s).'
E_CONF_RESTAUREE = 'Configuration restaurée (%s).'
E_ECRITURE_KO = 'Écriture impossible : %s'
E_PROPRES_APPAREIL = "%d réglage(s) propre(s) à l'appareil d'origine ignoré(s) (pilote GPU) : le tien reste utilisé."
I_CONTENEUR = 'Conteneur invalide : %s (%s)'
I_CORROMPU = 'CORROMPU : contenu différent, taille ET date inchangées — %s'
I_MANQUANT = 'MANQUANT : %s'
I_MODIFIE = "Modifié (taille différente, normal si tu l'as remplacé) : %s"
I_REMPLACE = 'Remplacé depuis la dernière vérification : %s'
I_TERMINEE = 'Vérification terminée : %d fichier(s) sains, %d suspect(s), %d manquant(s).'
I_TOURNANTE = 'Vérification tournante : %d fichier(s) sur %d, %.1f Go.'
J_ERREUR = 'Erreur : %s'
J_NOTIF_KO = 'Notification impossible : %s'
NO_ECHOUEE = 'Notification vers %s échouée (%s)'
NO_ENVOYEE = 'Notification envoyée à %s'
N_CLES_TITRE = 'Clés de titre : %d ajoutée(s) dans title.keys.'
N_ECHEC = '  ÉCHEC %s : %s'
N_ECHEC_INCOMPLET = "  ÉCHEC %s : données incomplètes dans l'archive (%.1f Mo lus sur %.1f attendus)"
N_ETAT_SAUVE = 'État sauvegardé : %d fichier(s) déjà dans la NAND (_eden-backup/).'
N_ILLISIBLE = '  ignoré, fichier illisible : %s'
N_INCOMPLET = '  ignoré, téléchargement incomplet : %s'
N_INSTALLE = '  installé %s (%.1f Mo)'
N_INTROUVABLE = '%s introuvable sur la console (%s).'
N_TERMINE = 'Terminé : %d fichier(s) installé(s), %d déjà présent(s), %d clé(s) de titre.'
SC_DEMARRAGE_IGNOREE = 'Tâche de démarrage ignorée, une autre est en cours : %s'
SC_ERREUR = 'Erreur du planificateur : %s'
SC_IGNOREE = 'Tâche planifiée ignorée, une autre est en cours : %s'
SV_ACCES_LIGNE = '%-4s %-3d %6.1fms %s'
SV_API_CREEE = "Clé d'API créée : %s"
SV_API_REVOQUEE = "Clé d'API révoquée : %s"
SV_APPAIRAGE_DEMANDE = 'Appairage sans fil demandé vers %s'
SV_APPAIRAGE_REFUSE = 'Appairage refusé : %s'
SV_APPAIREE_CONNEXION_KO = 'Appairée, mais la connexion a été refusée : %s'
SV_AUDIT_KO = 'Audit de sécurité indisponible : %s'
SV_BASCULE_WIFI = 'Console basculée en Wi-Fi : %s'
SV_COMPTE_CREE = 'Compte créé : %s'
SV_CONF_RESTAUREE = 'Configuration restaurée : %s'
SV_CONNEXION = 'Connexion de %s'
SV_CONNEXION_DEPUIS = 'Connexion de %s depuis %s'
SV_CONNEXION_REFUSEE = 'Connexion refusée : %s'
SV_CONNEXION_REFUSEE_DE = 'Connexion refusée pour %s depuis %s : %s'
SV_CONSOLE_PRETE = 'Console appairée et connectée (%s).'
SV_DEPOT_KO = 'Dépôt indisponible (%s) : %s'
SV_DESTINATION_AJOUTEE = 'Destination de notification ajoutée : %s'
SV_EMULATEUR_DETECTE = 'Émulateur détecté sur la console : %s'
SV_ERREUR_APIV1 = 'Erreur API v1 sur %s : %s'
SV_ERREUR_SERVEUR = 'Erreur serveur sur %s : %s'
SV_FICHES_OUBLIEES = '%d fiche(s) oubliée(s) : elles seront retéléchargées.'
SV_GET_INCONNUE = 'Route GET inconnue : %s'
SV_INTERFACE_CONSOLE = 'Interface ouverte sur la console : %s'
SV_JETON_REFUSE = 'Jeton refusé depuis %s'
SV_LUDO = 'Ludothèque : %s'
SV_MDP_CHANGE = 'Mot de passe changé : %s'
SV_POST_INCONNUE = 'Route POST inconnue : %s (serveur à jour ?)'
SV_POST_REJETE = 'POST rejeté sur %s : origine %s'
SV_PURGE = 'Purge automatique : %d lot(s), %.1f Go libérés'
SV_QR_KO = 'QR non généré : %s'
SV_RECU_DEPOT = 'Reçu par glisser-déposer : %s'
SV_REFUSE = '%s refusé : %s'
SV_REQUETE_INVALIDE = 'Requête invalide sur %s : %s'
SV_SECURITE_POINT = 'Sécurité — %s : %s'
SV_SECURITE_POINTS = 'Sécurité : %d point(s) à regarder — `python3 -m romule.audit`'
S_ECHEC = '  Échec : %s'
S_ENREGISTREES = 'Sauvegardes enregistrées dans _saves/%s'
S_RECUPERATION = 'Récupération de %s…'
S_SAUVEGARDES = '  %d fichier(s) sauvegardé(s).'
N_LECTURE_DE = 'Lecture de %s…'
SV_ARRETE = 'Arrêté.'
SV_CONSOLE_RETROUVEE = 'Console retrouvée en Wi-Fi (%s).'
SV_CONSOLE_PAS_WIFI = 'Console absente du Wi-Fi (%s).'


# ------------------------------------------------ what the `romule` command says
# Whole PARAGRAPHS, not the hard-wrapped lines they used to be. A paragraph cut
# by hand at 62 characters wraps where French happens to end a word; translated,
# the same cuts land mid-clause. `cli.dire()` wraps at print time instead.
CLI_ACCES_OUVERT = 'Accès ouvert SANS MOT DE PASSE.'
CLI_AUTH_DESACTIVEE = "L'authentification (%s) est DÉSACTIVÉE."
CLI_COMPTES_INTACTS = (
    'Les comptes existent toujours : `romule access close` la remet en service.')
CLI_TOUS_LES_DROITS = (
    'Tout appareil capable de joindre cette adresse a tous les droits — y '
    'compris derrière un proxy inverse. Redémarre le service pour que ce soit '
    'pris en compte.')
CLI_REFUS_SANS_COMPTE = 'Refusé : aucun compte ni SSO utilisable.'
CLI_ENFERMER_DEHORS = (
    "Fermer l'accès maintenant enfermerait tout le monde dehors, toi compris. "
    "Crée d'abord un compte :")
CLI_ACCES_FERME = 'Accès sans mot de passe désactivé.'
CLI_SE_CONNECTER = 'Il faut désormais se connecter. Redémarre le service.'
CLI_ETAT_OUVERT = 'Accès : OUVERT sans mot de passe.'
CLI_ETAT_PROTEGE = 'Accès : protégé par %s.'
CLI_ETAT_NON_CHOISI = "Accès : PERSONNE N'A ENCORE CHOISI."
CLI_REPOND_A_TOUS = (
    "L'installation répond à tout le monde jusqu'à ce que l'étape « Ton accès »"
    " de l'assistant soit renseignée.")
CLI_ETAT_LOCAL = 'Accès : cette machine seulement.'
CLI_AIDE_OPEN = '  romule access open     ouvrir sans mot de passe'
CLI_AIDE_CLOSE = '  romule access close    exiger une connexion'
CLI_JETON_NOUVEAU = "Nouveau jeton d'accès :"
CLI_JETON_ANCIEN_MORT = (
    "L'ancien ne fonctionne plus. Les navigateurs qui l'avaient retenu "
    'redemanderont celui-ci au prochain chargement. Redémarre le service pour '
    "qu'il le prenne en compte.")
CLI_JETON_AUCUN = "Aucun jeton d'accès."
CLI_JETON_QUAND = (
    "Il n'en est engendré un que lorsque le service écoute sur le réseau sans "
    "compte ni SSO — sur cette machine seulement, il n'y a rien à protéger. "
    '`romule token reset` en pose un quand même.')
CLI_JETON_ACTUEL = "Jeton d'accès :"
CLI_JETON_OU_COLLER = "Colle-le dans l'écran d'accueil de l'interface."
CLI_CLE_CREEE = 'Clé créée : %s'
CLI_CLE_NOTE_LA = (
    "Note-la maintenant : elle n'est conservée que sous forme d'empreinte et ne "
    'pourra pas être réaffichée.')
CLI_CLE_REVOQUEE = 'Clé %s révoquée.'
CLI_CLE_INCONNUE = 'Aucune clé active avec cet identifiant : %s'
CLI_CLE_AUCUNE = 'Aucune clé. `romule apikey create <nom>` en crée une.'
CLI_ROOT_CREATION_KO = 'Impossible de créer le dossier de données : %s'
CLI_ROOT_LECTURE_SEULE = "Le dossier de données n'est pas inscriptible :"
CLI_ROOT_A_QUOI = 'Romule y écrit sa configuration, ses comptes et ses journaux.'
CLI_ROOT_CONTENEUR = (
    "En conteneur, c'est presque toujours l'identifiant du propriétaire : "
    "l'image tourne sous 1000:1000.")
CLI_ROOT_CONTENEUR_SUITE = (
    'ou adapte `user:` dans docker-compose.yml à ton identifiant '
    '(`id -u` / `id -g`). Un volume nommé évite la question.')
CLI_ROOT_DESIGNE = 'Le dossier de données désigne %s :'
CLI_ROOT_EXPLICITE = 'Indique un dossier de données explicite :'
CLI_ROOT_JEUX_AILLEURS = "Le dossier des JEUX, lui, se choisit dans l'interface."
CLI_AUCUN_COMPTE_PREMIER = 'Aucun compte. Le premier créé sera administrateur.'
CLI_AUTH_INTERNE_ACTIVEE = 'Authentification interne activée. Redémarre le service.'
CLI_AUTH_INACTIVE = (
    "Note : l'authentification n'est pas active (Réglages > Accès, ou "
    '`romule access close`).')
CLI_REFUSE = 'Refusé : %s'
CLI_MDP_REPOSE = 'Mot de passe reposé pour %s.'
CLI_SESSIONS_INVALIDEES = 'Toutes les sessions ouvertes de ce compte sont invalidées.'
CLI_COMPTEUR_REMIS = "Le compteur d'échecs et le blocage éventuel sont remis à zéro."
CLI_COMPTE_INCONNU = 'Aucun compte avec cette adresse.'
CLI_EST_ADMIN = '%s est désormais administrateur.'
CLI_NEST_PLUS_ADMIN = "%s n'est plus administrateur."
CLI_2FA_RETIRE = 'Second facteur retiré pour %s.'
CLI_2FA_ABSENT = "Ce compte n'avait pas de second facteur actif."
CLI_SUPPRESSION_DEFINITIVE = 'Ceci supprimera définitivement %s.'
CLI_CONFIRMER_OUI = 'Relance avec --oui pour confirmer.'
CLI_COMPTE_SUPPRIME = 'Compte supprimé : %s'
CLI_RAPPORT_SANS_SECRET = (
    'Colle ce rapport dans un ticket : il ne contient ni mot de passe, ni clé, '
    "ni adresse de webhook.")
CLI_RIEN_A_ENVOYER = 'Aucun .nsp/.xci à envoyer.'
CLI_BRANCHE_USB = 'Branche le handheld en USB et autorise le débogage.'


# -------------------------------- what a wireless connection actually ends as
D_LIEN_HORS_LIGNE = (
    "La console a accepté la connexion puis l'a laissée retomber. Le port de "
    'connexion change à chaque redémarrage du débogage sans fil : relis-le sur '
    "l'écran de la console. Si c'est le bon, coupe et rallume le débogage sans "
    'fil.')
D_LIEN_NON_AUTORISE = (
    "La console demande ton autorisation : regarde son écran et accepte « "
    'Autoriser le débogage USB ». Coche « Toujours autoriser » pour ne plus '
    'avoir à le refaire.')
D_LIEN_ABSENT = (
    "adb a dit « connecté », puis la console n'est apparue dans aucune liste. "
    "L'adresse répond mais ce n'est pas une console en débogage sans fil.")


# ------------------------------------------- the USB port, seen from the wizard
USB_PRET = 'Console détectée : %s.'
USB_AUTORISATION = "Console branchée, en attente de ton autorisation sur son écran."
USB_AUCUNE = 'Aucune console vue sur le port USB.'
USB_INVISIBLE = "Le port USB n'est pas visible depuis ce conteneur."
SV_APPAIREE_PORT_INCONNU = (
    "Appairée. Il reste son port de connexion, que seule la console "
    'affiche.')
SV_APPAIREE_PORT_INCONNU_LOG = (
    'Appairée, mais aucune adresse de connexion trouvée (essayées : %s).')
SV_CONNEXION_DEMANDEE = 'Connexion sans fil demandée vers %s'
SV_CONNEXION_REFUSEE_ADR = 'Connexion refusée vers %s : %s'
