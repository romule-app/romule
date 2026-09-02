"""Authentification OpenID Connect (SSO), sans aucune dependance.

Flux retenu : « Authorization Code + PKCE », le seul recommande aujourd'hui pour
une application qui detient un secret ET tourne dans un navigateur. Il fonctionne
avec tous les fournisseurs auto-heberges courants — Authentik, Keycloak, Zitadel,
Authelia, Pocket ID — car il ne repose que sur la decouverte standard
`/.well-known/openid-configuration`.

Ce qui est verifie a chaque connexion, dans cet ordre :
  1. `state`  : la reponse correspond bien a une demande que NOUS avons emise
     (protege du CSRF sur le point de retour) ;
  2. le code est echange contre des jetons, en TLS, en presentant le
     `code_verifier` (PKCE) : un code intercepte ne suffit pas ;
  3. la signature RS256 de l'`id_token` est verifiee contre la cle publique
     publiee par le fournisseur (JWKS) ;
  4. `iss`, `aud`, `exp`, `iat` et `nonce` sont controles ;
  5. si une liste d'utilisateurs autorises est configuree, l'identite doit y
     figurer — un fournisseur peut authentifier bien plus de monde que ce que
     l'on veut laisser entrer ici.

La session tient dans un cookie signe (HMAC-SHA256) : pas d'etat serveur, donc
un redemarrage ne deconnecte personne, et rien n'est stocke sur disque hormis le
secret de signature.

Rien de tout cela ne s'active tant que `auth_mode` ne vaut pas "oidc".
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
import urllib.request

from . import config, reseau

DUREE_SESSION = 12 * 3600      # au-dela, il faut repasser par le fournisseur
# Duree du « pont » remis a celui qui vient d'activer
# l'authentification : juste de quoi finir de se configurer.
DUREE_PONT = 30 * 60
DUREE_TRANSIT = 10 * 60        # duree de vie d'une demande de connexion en cours
_DECOUVERTE = {}               # cache {issuer: (expiration, document)}
_JWKS = {}                     # cache {uri: (expiration, cles)}


# --------------------------------------------------------------- petits outils

def _b64url_decode(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _secret():
    """Secret de signature des cookies, cree une fois puis conserve."""
    cfg = config.load_config()
    s = cfg.get("auth_secret") or ""
    if not s:
        s = secrets.token_urlsafe(32)
        cfg["auth_secret"] = s
        config.save_config(cfg)
    return s.encode("utf-8")


def _signer(charge):
    """Encode un dict en jeton signe `corps.signature`, sans etat serveur."""
    corps = _b64url(json.dumps(charge, separators=(",", ":")).encode("utf-8"))
    sig = _b64url(hmac.new(_secret(), corps.encode("ascii"), hashlib.sha256).digest())
    return corps + "." + sig


def _verifier(jeton):
    """Renvoie la charge si la signature ET l'expiration tiennent, sinon None."""
    try:
        corps, sig = str(jeton).split(".", 1)
    except ValueError:
        return None
    attendu = _b64url(hmac.new(_secret(), corps.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, attendu):
        return None
    try:
        d = json.loads(_b64url_decode(corps))
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("exp", 0) < time.time():
        return None
    return d


def _http_json(url, donnees=None, entetes=None, timeout=15):
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(donnees).encode() if donnees else None,
        headers=entetes or {"Accept": "application/json"})
    with reseau.ouvrir(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# --------------------------------------------------------------- decouverte

def decouverte(issuer, force=False):
    """Document de configuration du fournisseur, mis en cache une heure."""
    issuer = (issuer or "").rstrip("/")
    if not issuer:
        raise ValueError("Aucune adresse de fournisseur configuree.")
    cache = _DECOUVERTE.get(issuer)
    if cache and not force and cache[0] > time.time():
        return cache[1]
    doc = _http_json(issuer + "/.well-known/openid-configuration")
    for champ in ("authorization_endpoint", "token_endpoint", "issuer"):
        if not doc.get(champ):
            raise ValueError("Reponse du fournisseur incomplete : %s manquant." % champ)
    _DECOUVERTE[issuer] = (time.time() + 3600, doc)
    return doc


def _cles(uri, kid, force=False):
    """Cle publique JWKS correspondant au `kid`, avec un rafraichissement unique
    si la cle est inconnue : les fournisseurs font tourner leurs cles."""
    cache = _JWKS.get(uri)
    if not cache or force or cache[0] <= time.time():
        doc = _http_json(uri)
        cache = (time.time() + 3600, doc.get("keys") or [])
        _JWKS[uri] = cache
    for k in cache[1]:
        if k.get("kid") == kid or not kid:
            return k
    return None if force else _cles(uri, kid, force=True)


# --------------------------------------------------------------- verification JWT

# Prefixe DER d'un DigestInfo SHA-256 (RFC 8017, EMSA-PKCS1-v1_5).
_DER_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _rs256_ok(signe, signature, jwk):
    """Verifie une signature RS256 avec la seule bibliotheque standard.

    RSA en verification se resume a `sig^e mod n`, puis a comparer le resultat
    au bourrage PKCS#1 v1.5 attendu. La comparaison est faite en temps constant.
    """
    try:
        n = int.from_bytes(_b64url_decode(jwk["n"]), "big")
        e = int.from_bytes(_b64url_decode(jwk["e"]), "big")
    except (KeyError, ValueError):
        return False
    taille = (n.bit_length() + 7) // 8
    if len(signature) != taille:
        return False
    clair = pow(int.from_bytes(signature, "big"), e, n).to_bytes(taille, "big")
    empreinte = hashlib.sha256(signe).digest()
    suffixe = _DER_SHA256 + empreinte
    bourrage = taille - len(suffixe) - 3
    if bourrage < 8:
        return False
    attendu = b"\x00\x01" + b"\xff" * bourrage + b"\x00" + suffixe
    return hmac.compare_digest(clair, attendu)


def verifier_id_token(jeton, doc, client_id, nonce):
    """Controle complet de l'`id_token`. Renvoie ses claims, ou leve ValueError."""
    try:
        e64, c64, s64 = jeton.split(".")
        entete = json.loads(_b64url_decode(e64))
        claims = json.loads(_b64url_decode(c64))
        signature = _b64url_decode(s64)
    except (ValueError, TypeError) as exc:
        raise ValueError("Jeton d'identite illisible.") from exc

    alg = entete.get("alg")
    if alg != "RS256":
        # On refuse tout le reste, `none` en premier lieu : accepter l'algorithme
        # annonce par le jeton lui-meme est la faille classique de JWT.
        raise ValueError("Algorithme de signature non pris en charge : %s." % alg)
    jwks_uri = doc.get("jwks_uri")
    if not jwks_uri:
        raise ValueError("Le fournisseur ne publie pas ses cles (jwks_uri).")
    jwk = _cles(jwks_uri, entete.get("kid"))
    if not jwk or not _rs256_ok((e64 + "." + c64).encode("ascii"), signature, jwk):
        raise ValueError("Signature du jeton d'identite invalide.")

    maintenant = time.time()
    if claims.get("iss", "").rstrip("/") != doc["issuer"].rstrip("/"):
        raise ValueError("Emetteur du jeton inattendu.")
    aud = claims.get("aud")
    aud = aud if isinstance(aud, list) else [aud]
    if client_id not in aud:
        raise ValueError("Ce jeton ne nous est pas destine.")
    if claims.get("exp", 0) < maintenant - 60:
        raise ValueError("Jeton expire.")
    if claims.get("iat", 0) > maintenant + 300:
        raise ValueError("Jeton date du futur : verifie l'horloge du serveur.")
    if nonce and claims.get("nonce") != nonce:
        raise ValueError("Nonce inattendu : la reponse ne correspond pas a la demande.")
    return claims


# --------------------------------------------------------------- flux

def actif(cfg=None):
    """L'authentification n'est active que si elle est UTILISABLE.

    Un mode « oidc » sans fournisseur renseigne — ou un mode « interne » sans
    aucun compte — refuserait tout le monde sans offrir de moyen de se
    connecter : l'utilisateur serait enferme dehors, y compris depuis sa propre
    machine. Une authentification a moitie configuree n'en est pas une : on la
    considere inactive tant qu'il n'existe pas un chemin d'entree reel.
    """
    cfg = cfg or config.load_config()
    mode = cfg.get("auth_mode")
    if mode == "interne":
        from . import comptes
        return comptes.nombre() > 0
    if mode == "oidc":
        return bool((cfg.get("oidc_issuer") or "").strip()
                    and (cfg.get("oidc_client_id") or "").strip())
    return False


def mode(cfg=None):
    """Mode reellement en vigueur : "aucun", "interne" ou "oidc"."""
    cfg = cfg or config.load_config()
    return cfg.get("auth_mode", "aucun") if actif(cfg) else "aucun"


def incomplet(cfg=None):
    """Mode demande, mais configuration insuffisante : a signaler."""
    cfg = cfg or config.load_config()
    return cfg.get("auth_mode") in ("oidc", "interne") and not actif(cfg)


def _reglages(cfg):
    manque = [c for c in ("oidc_issuer", "oidc_client_id") if not (cfg.get(c) or "").strip()]
    if manque:
        raise ValueError("Configuration incomplete : %s." % ", ".join(manque))
    return (cfg["oidc_issuer"].strip(), cfg["oidc_client_id"].strip(),
            (cfg.get("oidc_client_secret") or "").strip())


def demarrer(cfg, redirect_uri):
    """Prepare une connexion. Renvoie (url_du_fournisseur, cookie_de_transit)."""
    issuer, client_id, _ = _reglages(cfg)
    doc = decouverte(issuer)
    etat = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    defi = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": (cfg.get("oidc_scopes") or "openid profile email").strip(),
        "state": etat,
        "nonce": nonce,
        "code_challenge": defi,
        "code_challenge_method": "S256",
    }
    transit = _signer({"etat": etat, "nonce": nonce, "verif": verifier,
                       "uri": redirect_uri, "exp": time.time() + DUREE_TRANSIT})
    return doc["authorization_endpoint"] + "?" + urllib.parse.urlencode(params), transit


def terminer(cfg, params, cookie_transit, redirect_uri):
    """Traite le retour du fournisseur. Renvoie (cookie_session, identite).

    Leve ValueError avec un message affichable en cas de refus.
    """
    if params.get("error"):
        raise ValueError("Le fournisseur a refuse la connexion : %s."
                         % params.get("error_description") or params["error"])
    attendu = _verifier(cookie_transit)
    if not attendu:
        raise ValueError("Demande de connexion expiree ou inconnue. Recommence.")
    if not hmac.compare_digest(str(params.get("state") or ""), attendu["etat"]):
        raise ValueError("Reponse inattendue (state) : connexion abandonnee.")
    if attendu.get("uri") != redirect_uri:
        raise ValueError("L'adresse de retour ne correspond pas a la demande.")
    code = params.get("code")
    if not code:
        raise ValueError("Aucun code d'autorisation dans la reponse.")

    issuer, client_id, secret = _reglages(cfg)
    doc = decouverte(issuer)
    donnees = {"grant_type": "authorization_code", "code": code,
               "redirect_uri": redirect_uri, "client_id": client_id,
               "code_verifier": attendu["verif"]}
    entetes = {"Accept": "application/json",
               "Content-Type": "application/x-www-form-urlencoded"}
    if secret:
        # `client_secret_basic` est la methode par defaut du standard ; on
        # bascule sur `client_secret_post` si le fournisseur l'exige.
        methodes = doc.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
        if "client_secret_basic" in methodes:
            jeton = base64.b64encode(
                ("%s:%s" % (urllib.parse.quote(client_id), urllib.parse.quote(secret)))
                .encode()).decode()
            entetes["Authorization"] = "Basic " + jeton
        else:
            donnees["client_secret"] = secret
    try:
        rep = _http_json(doc["token_endpoint"], donnees, entetes)
    except Exception as exc:                      # reseau, 4xx, JSON invalide
        raise ValueError("Echange du code impossible : %s" % exc) from exc

    id_token = rep.get("id_token")
    if not id_token:
        raise ValueError("Le fournisseur n'a pas renvoye de jeton d'identite.")
    claims = verifier_id_token(id_token, doc, client_id, attendu["nonce"])

    identite = {
        "sub": claims.get("sub", ""),
        "nom": claims.get("name") or claims.get("preferred_username") or claims.get("email") or "",
        "email": (claims.get("email") or "").lower(),
        "groupes": claims.get("groups") if isinstance(claims.get("groups"), list) else [],
    }
    _verifier_autorisation(cfg, identite)
    identite["admin"] = est_admin_oidc(cfg, identite)
    # Le role est fige DANS le jeton, donc pour la duree de la session (12 h).
    # Le relire a chaque requete demanderait de rappeler le fournisseur : ici
    # on inscrit ce qu'il a dit au moment de la connexion. Retirer quelqu'un
    # d'un groupe le declasse a sa prochaine session, pas au milieu de
    # celle-ci — c'est le comportement de la plupart des SSO, et il est dit
    # dans la documentation plutot que suppose.
    session = _signer({"sub": identite["sub"], "nom": identite["nom"],
                       "email": identite["email"], "src": "oidc",
                       "admin": bool(identite["admin"]),
                       "exp": time.time() + DUREE_SESSION})
    return session, identite


def est_admin_oidc(cfg, identite):
    """Ce compte SSO a-t-il le role d'administrateur ?

    `oidc_groupes` dit QUI PEUT ENTRER ; `oidc_admin_groupes` dit QUI
    ADMINISTRE. Ce sont deux questions differentes, et les confondre donnerait
    l'administration a tout le monde — c'est l'erreur qui rendrait le modele de
    roles decoratif.

    Sans `oidc_admin_groupes`, AUCUNE session SSO n'est administratrice. Le
    defaut refuse : un reglage vide ne doit jamais valoir « tout le monde ».
    """
    voulus = [x.strip().lower()
              for x in str(cfg.get("oidc_admin_groupes") or "")
              .replace(";", ",").split(",") if x.strip()]
    if not voulus:
        return False
    siens = {str(g).lower() for g in (identite.get("groupes") or [])}
    return bool(siens & set(voulus))


def _verifier_autorisation(cfg, identite):
    """Authentifie n'est pas autorise : le fournisseur connait souvent bien plus
    de comptes que ceux qui doivent acceder a CET outil."""
    def liste(cle):
        v = cfg.get(cle) or ""
        return [x.strip().lower() for x in str(v).replace(";", ",").split(",") if x.strip()]

    emails, groupes = liste("oidc_emails"), liste("oidc_groupes")
    if not emails and not groupes:
        return                                   # aucune restriction demandee
    if emails and identite["email"] in emails:
        return
    if groupes and {g.lower() for g in identite["groupes"]} & set(groupes):
        return
    raise ValueError("Ce compte n'est pas autorise a acceder a cette ludotheque.")


def session_interne(u):
    """Cookie de session pour un compte interne.

    `mdp` porte l'instant du dernier changement de mot de passe. Toute session
    signee avant ce moment est refusee : changer son mot de passe deconnecte
    donc les autres appareils, y compris celui d'un intrus.
    """
    return _signer({"sub": u["id"], "nom": u.get("nom") or u["email"],
                    "email": u["email"], "src": "interne",
                    "mdp": u.get("maj_mdp", 0),
                    "exp": time.time() + DUREE_SESSION})


def session(cookie_header):
    """Identite de la session en cours, ou None."""
    for morceau in (cookie_header or "").split(";"):
        nom, _, valeur = morceau.strip().partition("=")
        if nom != "switch_session":
            continue
        d = _verifier(valeur)
        if d and d.get("src") == "interne":
            from . import comptes
            u = comptes.par_id(d.get("sub"))
            # Compte supprime, ou mot de passe change depuis : la session
            # signee ne vaut plus rien, meme si sa signature est bonne.
            if not u or u.get("maj_mdp", 0) != d.get("mdp"):
                return None
            d["photo"] = bool(u.get("photo"))
            d["nom"] = u.get("nom") or u["email"]
            d["email"] = u["email"]
        return d
    return None


def entete_cookie(valeur, secure, duree=None):
    parts = ["switch_session=" + (valeur or ""), "Path=/", "HttpOnly", "SameSite=Lax",
             "Max-Age=%d" % (0 if valeur == "" else (duree or DUREE_SESSION))]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def entete_transit(valeur, secure):
    parts = ["switch_oidc=" + (valeur or ""), "Path=/auth", "HttpOnly", "SameSite=Lax",
             "Max-Age=%d" % (0 if valeur == "" else DUREE_TRANSIT)]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def transit(cookie_header):
    for morceau in (cookie_header or "").split(";"):
        nom, _, valeur = morceau.strip().partition("=")
        if nom == "switch_oidc":
            return valeur
    return ""


def tester(cfg):
    """Verifie que le fournisseur repond et publie ce qu'il faut."""
    issuer, client_id, secret = _reglages(cfg)
    doc = decouverte(issuer, force=True)
    cles = []
    if doc.get("jwks_uri"):
        try:
            cles = _http_json(doc["jwks_uri"]).get("keys") or []
        except Exception:
            cles = []
    return {
        "issuer": doc.get("issuer"),
        "autorisation": doc.get("authorization_endpoint"),
        "jetons": doc.get("token_endpoint"),
        "cles": len(cles),
        "pkce": "S256" in (doc.get("code_challenge_methods_supported") or []),
        "secret": bool(secret),
        "client_id": client_id,
    }
