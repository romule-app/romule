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
