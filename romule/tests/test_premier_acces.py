"""An exposed service must be usable on the first try — and claimable once.

The defect this file was written for: a container binds to 0.0.0.0, otherwise
it would be unreachable from the host. With no account, no token and no
`lan_access`, every remote request was refused — with a message inviting you to
"enable access in the settings", settings you could precisely not reach.

The first answer was a generated token, printed in the logs. It broke the
deadlock and built a worse one: it had to be copied onto every device, and the
FIRST ACCOUNT still could not be created, because that was refused unless the
request came from 127.0.0.1 — which under Docker is nobody. `romule user` had
no `create` either. The main installation path ended in a wall no token opened.

So the deadlock is broken where it belongs. An installation nobody has claimed
answers everybody, and the wizard's access step — an account, or no password —
is what claims it. Jellyfin, Home Assistant and the *arr stack all work this
way, and it needs no secret at all.

Five properties:

  1. an unclaimed installation answers, from anywhere, so the wizard is
     reachable from the device you are actually holding;
  2. it SAYS SO in the terminal, loudly, rather than leaving it to be found;
  3. creating the first account claims it — and switches the authentication on,
     because an account that guards nothing is not an answer;
  4. choosing "no password" claims it too, deliberately;
  5. the terminal can always reopen and reclose the door, because the day the
     interface is unreachable is the day you need it.
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
# The token is printed on its own line now, not inside an address. A container
# cannot know the address anyone reaches it at (see `server._lan_ip`), and a
# secret reprinted at every restart ends up in every log attached to a bug
# report. So: the string, once, and a field in the interface to paste it into.
# The token is announced on the line that FOLLOWS the instruction, and only
# there. Anchoring on the instruction rather than on the shape of the string is
# what stops the test's own temporary folder — `/var/folders/7c/rv0vjgfj36bc…`
# on macOS — from passing for a secret, which it did.
ANNONCE = re.compile(r"colle ce jeton[^\n]*\n[^\n]*?([A-Za-z0-9_-]{30,})", re.I)


def jeton_de(sortie):
    """The announced token, or "" when nothing was announced."""
    m = ANNONCE.search(sortie)
    return m.group(1) if m else ""

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c:
        ok += 1
        print("      OK   %s" % n)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (n, d))


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


def adresse_reseau():
    """This machine's address ON the network, or None.

    Querying 127.0.0.1 proves nothing: that address is local by definition, so
    always allowed. The refusal can only be observed from an address the server
    does not recognise as its own.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))     # reseau de documentation : aucun paquet
            a = s.getsockname()[0]
        return None if a.startswith("127.") else a
    except OSError:
        return None


def demarrer(racine, port, **env):
    """Starts a server capturing its output: the token is in there."""
    srv = subprocess.Popen(
        [sys.executable, "-u", "-m", "romule", "serve"], cwd=RACINE_PROJET,
        env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=port,
                 ROMULE_NO_BROWSER="1", **env),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:" + port
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=5)
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            if srv.poll() is not None:
                break
            time.sleep(0.5)
    return srv, base


def arreter(srv):
    """Returns the server's full output, once it has finished writing."""
    srv.terminate()
    try:
        return srv.communicate(timeout=20)[0] or ""
    except subprocess.TimeoutExpired:
        srv.kill()
        return srv.communicate()[0] or ""


def conf_de(racine):
    """The configuration on disk, or {} when there is none.

    There often is none now: nothing is written at startup any more. The token
    generation was what created the file, and its absence is itself a small
    proof that no secret is being invented.
    """
    f = Path(racine) / "_romule-config.json"
    return json.loads(f.read_text()) if f.exists() else {}


def code(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as x:
        return x.code
    except Exception:
        return 0


print("   -- 1. une installation que personne n'a revendiquee --")
racine = tempfile.mkdtemp(prefix="ludo-acces-")
port = libre()
srv, base = demarrer(racine, port, ROMULE_BIND="0.0.0.0")
reseau = adresse_reseau()
distant = "http://%s:%s" % (reseau, port) if reseau else None
sans = code(distant + "/") if distant else None
sante = json.loads(urllib.request.urlopen(base + "/api/health", timeout=20).read())
sortie = arreter(srv)

if distant:
    # THE property. Under Docker the person installing it is never 127.0.0.1,
    # so anything stricter than this is a wall with nobody behind it.
    t("depuis le reseau, sans rien : la page repond", sans == 200,
      "recu %s" % sans)
else:
    print("      (pas d'adresse reseau sur cette machine : non verifiable)")
t("l'assistant est ce qu'il faut remplir", sante.get("first_run") is True, sante)
t("et l'acces n'est pas encore choisi",
  sante["checks"].get("acces_choisi") is False, sante["checks"])

# Said out loud: an open installation that says nothing is a trap.
t("le terminal previent que rien n'est protege",
  "PERSONNE N'A ENCORE CHOISI" in sortie, sortie[-400:])
t("et dit ou repondre", "assistant" in sortie.lower(), sortie[-400:])
# No secret is invented any more.
t("aucun jeton n'est engendre", not jeton_de(sortie) and "?token=" not in sortie)
conf = conf_de(racine)
t("ni conserve sur disque", not (conf.get("jeton_auto") or "").strip())

print("   -- 2. creer le premier compte revendique l'installation --")
port2 = libre()
srv, base2 = demarrer(racine, port2, ROMULE_BIND="0.0.0.0")
distant2 = "http://%s:%s" % (reseau, port2) if reseau else base2


def poster(url, charge, entetes=None):
    """(code, body) for a JSON POST, without following the redirect."""
    e = {"Content-Type": "application/json", "Origin": url.rsplit("/api", 1)[0]}
    e.update(entetes or {})
    req = urllib.request.Request(url, data=json.dumps(charge).encode(), headers=e)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as x:
        return x.code, x.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, str(exc)


# The wall this whole redesign is about: from the Docker bridge, not localhost.
c, corps = poster(distant2 + "/api/compte-creer",
                  {"email": "toi@exemple.fr", "mdp": "UnMotDePasseAssezLong9"})
t("le premier compte se cree depuis le reseau", c == 200, "%s %s" % (c, corps[:120]))
conf2 = conf_de(racine)
# An account that guards nothing is not an answer.
t("l'authentification est activee du meme geste",
  conf2.get("auth_mode") == "interne", conf2.get("auth_mode"))
t("et l'acces est marque comme choisi", conf2.get("acces_choisi") is True)
t("l'acces sans mot de passe est referme", conf2.get("lan_access") is False)
apres = code(distant2 + "/") if distant else None
if distant:
    t("il faut desormais se connecter", apres == 401, "recu %s" % apres)
# A second one cannot be claimed from outside.
c2, _ = poster(distant2 + "/api/compte-creer",
               {"email": "autre@exemple.fr", "mdp": "UnMotDePasseAssezLong9"})
# 401 rather than 403: the request is not authenticated at all now, so it is
# turned away before the administrator check is even reached. Either code says
# the same thing — it is no longer open to whoever asks.
t("un second compte n'est plus ouvert a tous", c2 in (401, 403), "recu %s" % c2)
arreter(srv)

print("   -- 3. l'autre reponse : aucun mot de passe --")
racine3 = tempfile.mkdtemp(prefix="ludo-acces-ouvert-")
port3 = libre()
srv, base3 = demarrer(racine3, port3, ROMULE_BIND="0.0.0.0")
distant3 = "http://%s:%s" % (reseau, port3) if reseau else base3
c, _ = poster(distant3 + "/api/acces-ouvert", {"ouvert": True})
t("le choix « sans mot de passe » est accepte", c == 200, "recu %s" % c)
conf3 = conf_de(racine3)
t("il est enregistre comme un choix", conf3.get("acces_choisi") is True
  and conf3.get("lan_access") is True, conf3)
if distant:
    t("et l'acces reste ouvert", code(distant3 + "/") == 200)
arreter(srv)

print("   -- 4. le terminal peut toujours rouvrir et refermer --")


def cli(racine, *args):
    return subprocess.run([sys.executable, "-m", "romule", *args],
                          cwd=RACINE_PROJET,
                          env=dict(os.environ, ROMULE_ROOT=racine),
                          capture_output=True, text=True)


# `close` with no way in left would lock out the person typing it.
r = cli(racine3, "access", "close")
t("fermer sans compte est refuse", r.returncode == 1 and "Refuse" in r.stdout,
  r.stdout[:120])
r = cli(racine3, "user", "create", "secours@exemple.fr",
        "--mdp", "UnMotDePasseAssezLong9")
t("un compte se cree depuis le terminal", "Compte cree" in r.stdout, r.stdout[:120])
t("et il active l'authentification",
  conf_de(racine3)
  .get("auth_mode") == "interne")
# `lan_access` alone reopens nothing while an authentication is active: the
# server consults the session first. An escape hatch that lies is worse than
# none, so `open` must switch it off too.
cli(racine3, "access", "open")
conf4 = conf_de(racine3)
t("rouvrir desactive vraiment l'authentification",
  conf4.get("auth_mode") == "aucun" and conf4.get("lan_access") is True, conf4)
cli(racine3, "access", "close")
conf5 = conf_de(racine3)
t("refermer la remet en service",
  conf5.get("auth_mode") == "interne" and conf5.get("lan_access") is False, conf5)

print("   -- 5. un jeton pose a la main protege toujours --")
# Nothing generates one any more, but `romule token reset` and ROMULE_TOKEN
# still do — and then the field that takes it must still be there.
racine4 = tempfile.mkdtemp(prefix="ludo-acces-champ-")
port4 = libre()
cli(racine4, "token", "reset")
srv, base4 = demarrer(racine4, port4, ROMULE_BIND="0.0.0.0")
distant4 = "http://%s:%s" % (reseau, port4) if reseau else base4


def page(url, donnees=None, entetes=None):
    """(code, body). A form POST, or a plain GET."""
    req = urllib.request.Request(
        url, data=donnees.encode() if donnees else None,
        headers=entetes or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as x:
        return x.code, x.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, str(exc)


c4, corps = page(distant4 + "/")
t("le refus est une page, pas une phrase", c4 == 401 and "<form" in corps,
  "%s %s" % (c4, corps[:120]))
t("elle porte un champ pour le jeton", "name='jeton'" in corps, corps[:200])
t("elle dit ou retrouver le jeton", "romule token show" in corps, corps[:400])
# Unstyled, the page arrived as black on white and read as a broken server.
# The stylesheet is the only file served before anyone has got in.
t("la feuille de style est joignable sans jeton",
  code(distant4 + "/app.css") == 200)
t("et rien d'autre ne l'est", code(distant4 + "/app.js") == 401,
  "recu %s" % code(distant4 + "/app.js"))

arreter(srv)
jeton4 = conf_de(racine4)["jeton_auto"]
srv, base4 = demarrer(racine4, port4, ROMULE_BIND="0.0.0.0")
entetes = {"Content-Type": "application/x-www-form-urlencoded",
           "Origin": distant4}
c_faux, _ = page(distant4 + "/auth/jeton", "jeton=pas-le-bon", entetes)
t("un jeton faux est refuse par le champ", c_faux == 401, "recu %s" % c_faux)
# The redirect must NOT be followed here. `urlopen` follows it by itself and
# drops the `Set-Cookie` on the way, so the final answer is the 401 of a
# browser that kept nothing — which says nothing about what we are checking.
class _SansSuivi(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


sans_suivi = urllib.request.build_opener(_SansSuivi)
req = urllib.request.Request(distant4 + "/auth/jeton",
                             data=("jeton=" + jeton4).encode(), headers=entetes)
try:
    with sans_suivi.open(req, timeout=20) as r:
        c_bon, cookie = r.status, r.headers.get("Set-Cookie") or ""
except urllib.error.HTTPError as x:
    c_bon, cookie = x.code, x.headers.get("Set-Cookie") or ""
t("le bon jeton fait entrer", c_bon == 302, "recu %s" % c_bon)
t("et le navigateur repart avec le cookie",
  "switch_token=" in cookie and "HttpOnly" in cookie, cookie[:90])
# A POST from elsewhere must not be able to plant the cookie.
c_ailleurs, _ = page(distant4 + "/auth/jeton", "jeton=" + jeton4,
                     {"Content-Type": "application/x-www-form-urlencoded",
                      "Origin": "http://ailleurs.invalid"})
t("une origine etrangere est rejetee", c_ailleurs == 403, "recu %s" % c_ailleurs)
arreter(srv)

print("   -- 6. renouveler le jeton depuis le terminal --")
avant = conf_de(racine4)["jeton_auto"]
cli(racine4, "token", "reset")
apres = conf_de(racine4)
t("le jeton change", apres["jeton_auto"] != avant and apres["jeton_auto"])
# Otherwise a new token nobody has been told about is a lock-out.
t("et il sera annonce au prochain demarrage",
  apres.get("jeton_annonce") is False, apres.get("jeton_annonce"))
montre = cli(racine4, "token", "show").stdout
t("`token show` redonne le nouveau", apres["jeton_auto"] in montre, montre[:120])

print("      ------------------------------------------------")
print("      %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
