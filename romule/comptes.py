"""Comptes internes : email + mot de passe, sans aucune dependance.

C'est l'alternative au SSO pour qui n'heberge pas de fournisseur OIDC. Les
choix de securite suivent les recommandations actuelles (NIST SP 800-63B,
OWASP ASVS v4 chapitre 2) :

  * empreintes `scrypt` — fonction a cout memoire, bien plus couteuse a
    attaquer par GPU qu'un simple SHA ; sel aleatoire par compte, parametres
    stockes avec l'empreinte pour pouvoir les durcir plus tard sans casser
    les comptes existants ;
  * comparaison a temps constant, et calcul d'une empreinte factice quand
    l'email est inconnu : le temps de reponse ne revele pas si un compte
    existe ;
  * un seul message d'erreur pour « email inconnu » et « mot de passe faux » ;
  * temporisation exponentielle apres echecs repetes, comptee a la fois par
    compte (persistee sur disque, donc un redemarrage ne l'efface pas) et par
    adresse IP ;
  * regle de mot de passe fondee sur la longueur et sur le refus des mots de
    passe courants, sans exigence de caracteres speciaux ni expiration —
    ces deux dernieres pratiques sont aujourd'hui deconseillees ;
  * changer son mot de passe invalide toutes les sessions ouvertes ailleurs.

Le fichier des comptes est distinct de la configuration : il ne doit jamais
partir dans une sauvegarde de reglages ni s'afficher dans l'interface. Il est
ecrit en 0600, et le dossier des photos en 0700.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import unicodedata

from . import config

FICHIER = config.fichier_etat("_romule-comptes.json", "_switch-comptes.json")
PHOTOS = config.ROOT / "_comptes"

# Parametres recommandes par l'OWASP (Password Storage Cheat Sheet) : N=2^17,
# r=8, p=1, soit 128 Mo de memoire et ~200 ms par calcul sur un Mac recent.
# C'est le cout memoire qui compte : il rend une attaque massive par GPU
# beaucoup plus chere qu'un simple SHA, quel que soit le nombre d'essais.
# Les parametres sont ecrits DANS l'empreinte : les relever plus tard
# n'invalidera aucun compte existant.
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 17, 8, 1, 32
SCRYPT_MAXMEM = 192 * 1024 * 1024

MDP_MIN, MDP_MAX = 12, 128
PHOTO_MAX = 2 * 1024 * 1024

# Seuil a partir duquel on temporise, et plafond de l'attente.
ECHECS_AVANT_ATTENTE = 3
ATTENTE_MAX = 15 * 60

_LOCK = threading.RLock()
_ECHECS_IP = {}                # {ip: (nombre, jusqu_a)} — memoire seule

# Les mots de passe les plus repandus dans les fuites publiques. La liste est
# volontairement courte : elle arrete les choix les plus evidents sans
# pretendre remplacer un service comme « Have I Been Pwned ».
COURANTS = {
    "password", "motdepasse", "123456", "12345678", "123456789", "1234567890",
    "azertyuiop", "qwertyuiop", "azerty123", "qwerty123", "motdepasse1",
    "password1", "password123", "administrateur", "administrator", "iloveyou",
    "bonjour123", "changeme", "letmein", "welcome1", "monmotdepasse",
    "abcd1234", "1qaz2wsx", "passw0rd", "p@ssw0rd", "motdepasse123",
    "nintendo", "nintendoswitch", "switch123", "ludotheque",
}


# ------------------------------------------------------------------ stockage

def _lire():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "comptes": []}
    if not isinstance(d, dict) or not isinstance(d.get("comptes"), list):
        return {"version": 1, "comptes": []}
    return d


def _ecrire(d):
    """Ecriture atomique, en 0600 : les empreintes ne doivent etre lisibles
    que par le compte systeme qui fait tourner le serveur."""
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FICHIER)


def nombre():
    return len(_lire()["comptes"])


def _public(u):
    return {"id": u["id"], "email": u["email"], "nom": u.get("nom") or u["email"],
            "photo": bool(u.get("photo")), "cree": u.get("cree", 0),
            "derniere": u.get("derniere", 0),
            "admin": bool(u.get("admin")),
            "double_facteur": bool((u.get("totp") or {}).get("actif"))}


def liste():
    """Comptes existants, sans rien qui touche au mot de passe."""
    return [_public(u) for u in _lire()["comptes"]]


def par_id(uid):
    for u in _lire()["comptes"]:
        if u["id"] == uid:
            return u
    return None


def est_admin(uid):
    u = par_id(uid)
    return bool(u and u.get("admin"))


def promouvoir(uid, admin=True):
    """Donne ou retire le role d'administrateur."""
    with _LOCK:
        d = _lire()
        for u in d["comptes"]:
            if u["id"] == uid:
                if not admin and not any(
                        v.get("admin") for v in d["comptes"] if v["id"] != uid):
                    raise ValueError("Il doit rester au moins un administrateur.")
                u["admin"] = bool(admin)
                _ecrire(d)
                return _public(u)
    raise ValueError("Compte introuvable.")


def reprendre_roles():
    """Les comptes crees avant l'existence des roles n'en ont aucun.

    Sans reprise, une installation existante se retrouverait sans le moindre
    administrateur apres la mise a jour : plus personne ne pourrait toucher aux
    reglages. Le plus ancien compte, celui de l'installateur, le devient.
    """
    with _LOCK:
        d = _lire()
        if not d["comptes"] or any(u.get("admin") for u in d["comptes"]):
            return
        plus_ancien = min(d["comptes"], key=lambda u: u.get("cree", 0))
        plus_ancien["admin"] = True
        _ecrire(d)


def _index_email(d, email):
    for i, u in enumerate(d["comptes"]):
        if u["email"] == email:
            return i
    return -1


# ------------------------------------------------------------ mots de passe

def _normaliser(mdp):
    """NFKC : « é » tape au clavier ou compose donne la meme empreinte."""
    return unicodedata.normalize("NFKC", mdp or "")


# scrypt a N=2^17 mobilise environ 128 Mio par calcul. C'est voulu : c'est ce
# qui rend une attaque hors ligne couteuse. Mais rien ne limitait le nombre de
# calculs SIMULTANES — quelques tentatives de connexion en parallele suffisaient
# a epuiser la memoire du serveur, ce qui transformait une protection en levier.
# Deux a la fois : assez pour ne pas ralentir un usage normal, assez peu pour
# que le pire cas reste borne.
_PLACES_SCRYPT = threading.BoundedSemaphore(
    int(config.env("SCRYPT_PARALLELE", "2")))


def hacher(mdp):
    sel = secrets.token_bytes(16)
    with _PLACES_SCRYPT:
        dk = hashlib.scrypt(_normaliser(mdp).encode("utf-8"), salt=sel,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            dklen=SCRYPT_LEN, maxmem=SCRYPT_MAXMEM)
    return "scrypt$%d$%d$%d$%s$%s" % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(sel).decode(), base64.b64encode(dk).decode())


def verifier_mdp(mdp, empreinte):
    """Comparaison a temps constant. Faux pour toute empreinte illisible."""
    try:
        algo, n, r, p, sel, dk = str(empreinte).split("$")
        if algo != "scrypt":
            return False
        attendu = base64.b64decode(dk)
        with _PLACES_SCRYPT:
            calcule = hashlib.scrypt(
                _normaliser(mdp).encode("utf-8"), salt=base64.b64decode(sel),
                n=int(n), r=int(r), p=int(p), dklen=len(attendu),
                maxmem=SCRYPT_MAXMEM)
    except Exception:
        return False
    return hmac.compare_digest(calcule, attendu)


# Empreinte jetable, calculee une fois : sert a occuper le processeur aussi
# longtemps sur un email inconnu que sur un email connu.
_LEURRE = None


def _perdre_du_temps(mdp):
    global _LEURRE
    if _LEURRE is None:
        _LEURRE = hacher(secrets.token_urlsafe(32))
    verifier_mdp(mdp, _LEURRE)


def valider_mdp(mdp, email=""):
    """Leve ValueError avec un message affichable si le mot de passe ne va pas."""
    mdp = _normaliser(mdp)
    if len(mdp) < MDP_MIN:
        raise ValueError("Le mot de passe doit faire au moins %d caracteres."
                         % MDP_MIN)
    if len(mdp) > MDP_MAX:
        raise ValueError("Le mot de passe ne peut pas depasser %d caracteres."
                         % MDP_MAX)
    bas = mdp.lower()
    if bas in COURANTS:
        raise ValueError("Ce mot de passe figure parmi les plus utilises : "
                         "choisis-en un autre.")
    # Un mot de passe fait de la meme lettre repetee passe la regle de longueur
    # sans rien valoir.
    if len(set(bas)) < 5:
        raise ValueError("Ce mot de passe est trop repetitif.")
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in bas:
        raise ValueError("Le mot de passe ne doit pas contenir ton adresse email.")
    return mdp


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def valider_email(email):
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise ValueError("Adresse email invalide.")
    return e


# ------------------------------------------------------------- temporisation

def _attente(echecs):
    """1re, 2e, 3e essai : libre. Ensuite 2 s, 4 s, 8 s... plafonne."""
    if echecs < ECHECS_AVANT_ATTENTE:
        return 0
    return min(2 ** (echecs - ECHECS_AVANT_ATTENTE + 1), ATTENTE_MAX)


def _reste(jusqu_a):
    return max(0, int(jusqu_a - time.time()))


def _refus_temporise(secondes):
    if secondes >= 60:
        duree = "%d minute(s)" % ((secondes + 59) // 60)
    else:
        duree = "%d seconde(s)" % secondes
    return ValueError("Trop de tentatives. Reessaie dans %s." % duree)


def _verrou_ip(ip):
    n, jusqu_a = _ECHECS_IP.get(ip or "?", (0, 0))
    return _reste(jusqu_a)


def _echec_ip(ip):
    ip = ip or "?"
    n = _ECHECS_IP.get(ip, (0, 0))[0] + 1
    _ECHECS_IP[ip] = (n, time.time() + _attente(n))


# ----------------------------------------------------------------- operations

def creer(email, mdp, nom="", cfg=None):
    """Cree un compte. Leve ValueError si l'email est pris ou le mot de passe faible."""
    email = valider_email(email)
    valider_mdp(mdp, email)
    with _LOCK:
        d = _lire()
        if _index_email(d, email) >= 0:
            raise ValueError("Un compte existe deja avec cette adresse.")
        # Le PREMIER compte est administrateur. C'est la convention des outils
        # auto-heberges (Jellyfin, Immich, Paperless) : celui qui installe
        # gouverne. Sans role du tout, n'importe quel utilisateur pouvait
        # supprimer les autres ou eteindre l'authentification.
        premier = not d["comptes"]
        u = {"id": secrets.token_urlsafe(9), "email": email,
             "nom": (nom or "").strip()[:80] or email.split("@")[0],
             "hash": hacher(mdp), "cree": int(time.time()),
             "maj_mdp": int(time.time()), "echecs": 0, "bloque": 0,
             "photo": "", "derniere": 0, "admin": premier}
        d["comptes"].append(u)
        _ecrire(d)
    return _public(u)


class BesoinCode(ValueError):
    """Mot de passe bon, mais le second facteur manque ou ne correspond pas.

    Une exception distincte : le formulaire doit alors demander le code, sans
    refaire saisir le mot de passe. Elle n'est levee qu'apres verification du
    mot de passe, donc elle ne revele l'existence d'aucun compte.
    """


def totp_preparer(uid):
    """Cree un secret, pas encore actif : il ne le devient qu'une fois un code
    valide fourni. Sans cette etape, une application mal configuree
    verrouillerait le compte."""
    from . import totp
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            secret = totp.secret_neuf()
            d["comptes"][i]["totp"] = {"secret": secret, "actif": False, "utilises": []}
            _ecrire(d)
            return {"secret": secret, "lisible": totp.lisible(secret),
                    "uri": totp.uri(secret, u["email"])}
    raise ValueError("Compte introuvable.")


def totp_activer(uid, saisie):
    from . import totp
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            conf = u.get("totp") or {}
            if not conf.get("secret"):
                raise ValueError("Commence par générer un secret.")
            bon, compteur = totp.verifier(conf["secret"], saisie,
                                          utilises=set(conf.get("utilises") or []))
            if not bon:
                raise ValueError("Code incorrect. Vérifie l'heure de ton téléphone.")
            conf.update({"actif": True, "utilises": [compteur]})
            d["comptes"][i]["totp"] = conf
            _ecrire(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_desactiver(uid, mdp):
    """Exige le mot de passe : retirer un facteur est un affaiblissement."""
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verifier_mdp(mdp, u["hash"]):
                raise ValueError("Mot de passe incorrect.")
            d["comptes"][i]["totp"] = {}
            _ecrire(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_actif(u):
    return bool((u or {}).get("totp", {}).get("actif"))


def _consommer_code(email, compteur):
    """Memorise le compteur utilise pour interdire le rejeu du meme code."""
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            return
        conf = d["comptes"][i].get("totp") or {}
        vus = [c for c in (conf.get("utilises") or []) if c > compteur - 10]
        vus.append(compteur)
        conf["utilises"] = vus[-10:]
        d["comptes"][i]["totp"] = conf
        _ecrire(d)


def connecter(email, mdp, ip="", code=""):
    """Renvoie le compte si les identifiants sont bons, sinon leve ValueError.

    Le message d'erreur est le meme pour un email inconnu et un mot de passe
    faux : donner un message different revient a publier la liste des comptes.
    """
    reste = _verrou_ip(ip)
    if reste:
        raise _refus_temporise(reste)
    email = (email or "").strip().lower()
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        u = d["comptes"][i] if i >= 0 else None
        if u:
            attente = _reste(u.get("bloque", 0))
            if attente:
                raise _refus_temporise(attente)

    if not u:
        _perdre_du_temps(mdp)          # meme cout que pour un compte reel
        _echec_ip(ip)
        raise ValueError("Email ou mot de passe incorrect.")

    if not verifier_mdp(mdp, u["hash"]):
        _echec_ip(ip)
        with _LOCK:
            d = _lire()
            i = _index_email(d, email)
            if i >= 0:
                n = d["comptes"][i].get("echecs", 0) + 1
                d["comptes"][i]["echecs"] = n
                d["comptes"][i]["bloque"] = time.time() + _attente(n)
                _ecrire(d)
        raise ValueError("Email ou mot de passe incorrect.")

    # Mot de passe valide. S'il existe un second facteur, il reste a franchir :
    # les compteurs d'echec ne sont donc pas encore remis a zero.
    if totp_actif(u):
        from . import totp
        bon, compteur = totp.verifier(u["totp"]["secret"], code,
                                      utilises=set(u["totp"].get("utilises") or []))
        if not bon:
            _echec_ip(ip)
            raise BesoinCode("Code à usage unique requis." if not code
                             else "Code incorrect ou déjà utilisé.")
        _consommer_code(email, compteur)

    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i >= 0:
            d["comptes"][i]["echecs"] = 0
            d["comptes"][i]["bloque"] = 0
            d["comptes"][i]["derniere"] = int(time.time())
            _ecrire(d)
            u = d["comptes"][i]
    _ECHECS_IP.pop(ip or "?", None)
    return u


def changer_mdp(uid, ancien, nouveau):
    """Exige le mot de passe actuel : un cookie vole ne doit pas suffire a
    prendre le compte definitivement."""
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verifier_mdp(ancien, u["hash"]):
                raise ValueError("Mot de passe actuel incorrect.")
            valider_mdp(nouveau, u["email"])
            if verifier_mdp(nouveau, u["hash"]):
                raise ValueError("Le nouveau mot de passe est identique a l'ancien.")
            d["comptes"][i]["hash"] = hacher(nouveau)
            # Change l'epoque du compte : toutes les sessions signees avant
            # cet instant cessent d'etre valables (voir auth.session).
            d["comptes"][i]["maj_mdp"] = int(time.time())
            _ecrire(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def reinitialiser_mdp(email, nouveau):
    """Repose le mot de passe SANS connaitre l'ancien. Depuis le terminal seul.

    C'est la porte de secours d'un administrateur enferme dehors : plus de mot
    de passe, plus de second facteur, et personne d'autre pour promouvoir un
    compte. La seule alternative etait d'editer `_romule-comptes.json` a la
    main — c'est-a-dire de coller une empreinte scrypt calculee ailleurs, ce
    que personne ne fait correctement du premier coup.

    Elle n'est atteignable QUE par la ligne de commande, jamais par une route
    HTTP : une reinitialisation sans preuve d'identite est exactement ce qu'un
    attaquant cherche. Qui peut lancer `romule` a deja les droits du service,
    donc l'acces au fichier des comptes : la commande ne donne rien de plus
    que ce que le systeme de fichiers donnait deja, elle le rend seulement
    faisable sans se tromper.
    """
    email = valider_email(email)
    valider_mdp(nouveau, email)
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        d["comptes"][i]["hash"] = hacher(nouveau)
        # Coupe toutes les sessions en cours : si le compte a ete pris, le
        # reprendre ne doit pas laisser l'autre connecte.
        d["comptes"][i]["maj_mdp"] = int(time.time())
        # Un compte bloque par des echecs repetes doit repartir : sinon la
        # reinitialisation reussit et la connexion echoue quand meme.
        d["comptes"][i]["echecs"] = 0
        d["comptes"][i]["bloque"] = 0
        _ecrire(d)
        return _public(d["comptes"][i])


def desactiver_totp(email):
    """Retire le second facteur. Pour un telephone perdu, depuis le terminal.

    `totp_desactiver()` exige le mot de passe, ce qui est juste depuis
    l'interface. Ici on est deja sur la machine : exiger le mot de passe
    n'ajouterait aucune preuve, et l'exiger pour un compte dont on vient de
    perdre le second facteur enfermerait dehors pour de bon.
    """
    email = valider_email(email)
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        avait = bool((d["comptes"][i].get("totp") or {}).get("actif"))
        # `{}` plutot qu'une cle retiree : c'est ce que fait deja
        # `totp_desactiver`, et deux representations du meme etat finissent
        # toujours par diverger quelque part.
        d["comptes"][i]["totp"] = {}
        _ecrire(d)
        return avait


def par_email(email):
    """Le compte portant cette adresse, ou None. Pour la ligne de commande."""
    d = _lire()
    i = _index_email(d, valider_email(email))
    return _public(d["comptes"][i]) if i >= 0 else None


def modifier(uid, nom=None, email=None):
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if nom is not None:
                d["comptes"][i]["nom"] = str(nom).strip()[:80] or u["email"].split("@")[0]
            if email is not None:
                e = valider_email(email)
                j = _index_email(d, e)
                if j >= 0 and j != i:
                    raise ValueError("Un compte existe deja avec cette adresse.")
                d["comptes"][i]["email"] = e
            _ecrire(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def supprimer(uid):
    """Refuse de supprimer le dernier compte : plus personne ne pourrait entrer."""
    with _LOCK:
        d = _lire()
        if len(d["comptes"]) <= 1:
            raise ValueError("C'est le dernier compte : il doit rester quelqu'un "
                             "pour se connecter.")
        reste = [u for u in d["comptes"] if u["id"] != uid]
        if len(reste) == len(d["comptes"]):
            raise ValueError("Compte introuvable.")
        # « Il doit rester quelqu'un » ne suffit pas : il doit rester quelqu'un
        # QUI PEUT ADMINISTRER. Sinon les reglages deviennent inaccessibles
        # sans toucher au fichier des comptes a la main.
        if not any(u.get("admin") for u in reste):
            raise ValueError("C'est le dernier administrateur : promeus "
                             "quelqu'un d'autre avant de le supprimer.")
        d["comptes"] = reste
        _ecrire(d)
    for ext in (".png", ".jpg", ".gif", ".webp"):
        p = PHOTOS / (uid + ext)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return True


# ---------------------------------------------------------------- photo

# On ne se fie pas au type annonce par le navigateur : on lit les premiers
# octets. Un fichier renomme en .png ne passera pas.
SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"GIF87a", ".gif", "image/gif"),
    (b"GIF89a", ".gif", "image/gif"),
]


def _type_image(octets):
    for magie, ext, mime in SIGNATURES:
        if octets.startswith(magie):
            return ext, mime
    if octets[:4] == b"RIFF" and octets[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None, None


def photo_ecrire(uid, octets):
    if len(octets) > PHOTO_MAX:
        raise ValueError("Image trop lourde (maximum %d Mo)." % (PHOTO_MAX // 2 ** 20))
    ext, mime = _type_image(octets or b"")
    if not ext:
        raise ValueError("Format d'image non reconnu (PNG, JPEG, GIF ou WebP).")
    with _LOCK:
        d = _lire()
        i = next((k for k, u in enumerate(d["comptes"]) if u["id"] == uid), -1)
        if i < 0:
            raise ValueError("Compte introuvable.")
        PHOTOS.mkdir(parents=True, exist_ok=True)
        os.chmod(PHOTOS, 0o700)
        for vieux in (".png", ".jpg", ".gif", ".webp"):
            p = PHOTOS / (uid + vieux)
            if p.exists() and vieux != ext:
                try:
                    p.unlink()
                except OSError:
                    pass
        (PHOTOS / (uid + ext)).write_bytes(octets)
        d["comptes"][i]["photo"] = uid + ext
        _ecrire(d)
    return {"photo": uid + ext, "type": mime}


def photo_lire(uid):
    """(octets, type) de la photo, ou (None, None)."""
    u = par_id(uid)
    nom = (u or {}).get("photo") or ""
    if not nom:
        return None, None
    p = PHOTOS / nom
    # Le nom vient du fichier de comptes, mais on verifie tout de meme qu'il
    # reste dans le dossier prevu.
    try:
        p.resolve().relative_to(PHOTOS.resolve())
    except (ValueError, OSError):
        return None, None
    if not p.exists():
        return None, None
    _, mime = _type_image(p.read_bytes()[:16])
    return p.read_bytes(), mime or "application/octet-stream"


def photo_effacer(uid):
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] == uid:
                nom = u.get("photo") or ""
                d["comptes"][i]["photo"] = ""
                _ecrire(d)
                if nom:
                    try:
                        (PHOTOS / nom).unlink()
                    except OSError:
                        pass
                return True
    return False
