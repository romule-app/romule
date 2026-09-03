"""OpenID Connect (SSO) authentication, with no dependency at all.

The chosen flow is "Authorization Code + PKCE", the only one recommended today
for an application that holds a secret AND runs in a browser. It works with
every common self-hosted provider — Authentik, Keycloak, Zitadel, Authelia,
Pocket ID — because it relies only on the standard
`/.well-known/openid-configuration` discovery document.

What is checked on every login, in this order:
  1. `state`  : the response matches a request WE issued (protects the return
     point against CSRF);
  2. the code is exchanged for tokens, over TLS, presenting the
     `code_verifier` (PKCE): an intercepted code is not enough;
  3. the `id_token`'s RS256 signature is verified against the public key the
     provider publishes (JWKS);
  4. `iss`, `aud`, `exp`, `iat` and `nonce` are checked;
  5. if a list of allowed users is configured, the identity must appear in it —
     a provider can authenticate far more people than we want to let in here.

The session lives in a signed cookie (HMAC-SHA256): no server-side state, so a
restart logs nobody out, and nothing is stored on disk beyond the signing
secret.

None of this activates until `auth_mode` is set to "oidc".
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

DUREE_SESSION = 12 * 3600      # past this, back through the provider
# How long the "bridge" handed to whoever just switched authentication on
# lasts: just enough to finish configuring themselves.
DUREE_PONT = 30 * 60
DUREE_TRANSIT = 10 * 60        # lifetime of a login request in flight
_DECOUVERTE = {}               # cache {issuer: (expiry, document)}
_JWKS = {}                     # cache {uri: (expiration, cles)}


# --------------------------------------------------------------- petits outils

def _b64url_decode(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _secret():
    """Cookie signing secret, created once and then kept."""
    cfg = config.load_config()
    s = cfg.get("auth_secret") or ""
    if not s:
        s = secrets.token_urlsafe(32)
        cfg["auth_secret"] = s
        config.save_config(cfg)
    return s.encode("utf-8")


def _signer(charge):
    """Encode a dict as a signed `body.signature` token, with no server state."""
    corps = _b64url(json.dumps(charge, separators=(",", ":")).encode("utf-8"))
    sig = _b64url(hmac.new(_secret(), corps.encode("ascii"), hashlib.sha256).digest())
    return corps + "." + sig


def _verifier(jeton):
    """Return the payload if BOTH signature and expiry hold, otherwise None."""
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
    """The provider's configuration document, cached for an hour."""
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
    """The JWKS public key matching `kid`, with a single refresh if the key is
    unknown: providers rotate their keys."""
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

# DER prefix of a SHA-256 DigestInfo (RFC 8017, EMSA-PKCS1-v1_5).
_DER_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _rs256_ok(signe, signature, jwk):
    """Verify an RS256 signature using the standard library alone.

    RSA verification comes down to `sig^e mod n`, then comparing the result to
    the expected PKCS#1 v1.5 padding. The comparison is constant-time.
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
        # Everything else is refused, `none` first of all: trusting the
        # algorithm the token itself announces is the classic JWT hole.
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
    """Authentication is only active when it is USABLE.

    An "oidc" mode with no provider filled in — or an "interne" mode with no
    account at all — would refuse everybody while offering no way to log in:
    the user would be locked out, including from their own machine. A
    half-configured authentication is not one: we treat it as inactive until a
    real way in exists.
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
    """Mode requested, but the configuration is insufficient: worth flagging."""
    cfg = cfg or config.load_config()
    return cfg.get("auth_mode") in ("oidc", "interne") and not actif(cfg)


def _reglages(cfg):
    manque = [c for c in ("oidc_issuer", "oidc_client_id") if not (cfg.get(c) or "").strip()]
    if manque:
        raise ValueError("Configuration incomplete : %s." % ", ".join(manque))
    return (cfg["oidc_issuer"].strip(), cfg["oidc_client_id"].strip(),
            (cfg.get("oidc_client_secret") or "").strip())


def demarrer(cfg, redirect_uri):
    """Prepare a login. Returns (provider_url, transit_cookie)."""
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
    """Handle the provider's callback. Returns (session_cookie, identity).

    Raises ValueError with a displayable message on refusal.
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
        # `client_secret_basic` is the standard's default method; we switch
        # to `client_secret_post` when the provider demands it.
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
    # The role is frozen INSIDE the token, hence for the session's lifetime
    # (12 h). Re-reading it on every request would mean calling the provider
    # again; here we write down what it said at login time. Removing someone
    # from a group demotes them at their next session, not in the middle of
    # this one — the behaviour of most SSO integrations, and stated in the
    # documentation rather than assumed.
    session = _signer({"sub": identite["sub"], "nom": identite["nom"],
                       "email": identite["email"], "src": "oidc",
                       "admin": bool(identite["admin"]),
                       "exp": time.time() + DUREE_SESSION})
    return session, identite


def est_admin_oidc(cfg, identite):
    """Does this SSO account hold the administrator role?

    `oidc_groupes` says WHO MAY ENTER; `oidc_admin_groupes` says WHO
    ADMINISTERS. Two different questions, and confusing them would hand
    administration to everybody — the mistake that would make the role model
    decorative.

    Without `oidc_admin_groupes`, NO SSO session is an administrator. The
    default refuses: an empty setting must never mean "everybody".
    """
    voulus = [x.strip().lower()
              for x in str(cfg.get("oidc_admin_groupes") or "")
              .replace(";", ",").split(",") if x.strip()]
    if not voulus:
        return False
    siens = {str(g).lower() for g in (identite.get("groupes") or [])}
    return bool(siens & set(voulus))


def _verifier_autorisation(cfg, identite):
    """Authenticated is not authorised: the provider usually knows far more
    accounts than those meant to reach THIS tool."""
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
    """Session cookie for an internal account.

    `mdp` carries the moment of the last password change. Any session signed
    before that instant is refused: changing the password therefore logs out
    the other devices, an intruder's included.
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
            # Account deleted, or password changed since: the signed session
            # is worth nothing any more, even with a valid signature.
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
    """Check that the provider answers and publishes what it must."""
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
