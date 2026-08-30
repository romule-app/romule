"""Codes a usage unique (TOTP, RFC 6238), sans dependance.

Un mot de passe vole suffit a entrer. Un second facteur change cela : il faut
aussi l'appareil qui genere le code. C'est la seule protection qui tienne si la
ludotheque est joignable depuis l'exterieur.

Compatible avec toutes les applications courantes (Google Authenticator, Aegis,
Bitwarden, 1Password, Ente Auth) : HMAC-SHA1, pas de 30 secondes, 6 chiffres —
ce que ces applications supposent par defaut.

Deux precautions que l'algorithme seul ne donne pas :

  * **tolerance d'une fenetre** en arriere et en avant, parce que l'horloge du
    telephone et celle du Mac ne sont jamais exactement synchrones ;
  * **refus de rejouer un code deja utilise** : sans cela, un code intercepte
    reste valable jusqu'a 90 secondes.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

PAS = 30                 # duree de vie d'un code, en secondes
CHIFFRES = 6
TOLERANCE = 1            # fenetres acceptees de part et d'autre


def secret_neuf(octets=20):
    """Secret partage, en base32 sans remplissage — le format attendu par les
    applications d'authentification."""
    return base64.b32encode(secrets.token_bytes(octets)).decode("ascii").rstrip("=")


def _cle(secret):
    s = (secret or "").strip().replace(" ", "").upper()
    s += "=" * (-len(s) % 8)
    return base64.b32decode(s, casefold=True)


def code(secret, moment=None, decalage=0):
    """Code a 6 chiffres pour l'instant donne."""
    compteur = int((moment if moment is not None else time.time()) // PAS) + decalage
    empreinte = hmac.new(_cle(secret), struct.pack(">Q", compteur), hashlib.sha1).digest()
    # « troncature dynamique » de la RFC 4226 : les 4 derniers bits designent
    # l'endroit ou lire les 31 bits qui donnent le code.
    debut = empreinte[-1] & 0x0F
    valeur = struct.unpack(">I", empreinte[debut:debut + 4])[0] & 0x7FFFFFFF
    return str(valeur % (10 ** CHIFFRES)).zfill(CHIFFRES)


def verifier(secret, saisie, moment=None, utilises=None):
    """Vrai si `saisie` est un code valide et non deja consomme.

    `utilises` est l'ensemble des compteurs deja acceptes pour ce compte : on
    y ajoute celui qui vient de servir, ce qui interdit de rejouer le meme code.
    """
    propre = "".join(c for c in str(saisie or "") if c.isdigit())
    if len(propre) != CHIFFRES:
        return False, None
    base = int((moment if moment is not None else time.time()) // PAS)
    for d in range(-TOLERANCE, TOLERANCE + 1):
        # comparaison a temps constant : le code est un secret de courte duree
        if hmac.compare_digest(code(secret, moment, d), propre):
            compteur = base + d
            if utilises is not None and compteur in utilises:
                return False, None          # deja utilise : rejeu refuse
            return True, compteur
    return False, None


def uri(secret, email, emetteur="Ma ludotheque"):
    """Adresse `otpauth://` a saisir dans l'application d'authentification."""
    label = urllib.parse.quote("%s:%s" % (emetteur, email or "compte"))
    params = urllib.parse.urlencode({
        "secret": secret, "issuer": emetteur,
        "algorithm": "SHA1", "digits": CHIFFRES, "period": PAS})
    return "otpauth://totp/%s?%s" % (label, params)


def lisible(secret):
    """Secret decoupe par groupes de 4 : on le recopie a la main sans se perdre."""
    s = (secret or "").replace(" ", "")
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))
