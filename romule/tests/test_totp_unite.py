"""The second factor's clock tolerance, checked without network or real clock.

These assertions used to live in the HTTP journey, where they were doomed to be
flaky: the test asked there for "the code from 30 seconds ago" without being able
to know whether that window had already been used. When a window boundary fell
between the login and the check — roughly one time in five — the code named a
consumed window, the server refused it as a replay, and the failure looked like a
tolerance bug.

Here `moment` is supplied, so nothing moves under the test's feet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import totp

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def _run():
    global ok, fail
    ok = fail = 0
    secret = totp.secret_neuf()
    # A fixed instant, aligned on a window: no boundary can be crossed during
    # the test.
    T = 1_700_000_000 - (1_700_000_000 % totp.PAS)

    t("le code de l'instant est accepte", totp.verifier(secret, totp.code(secret, T), T)[0])
    t("la fenetre precedente est toleree",
      totp.verifier(secret, totp.code(secret, T - totp.PAS), T)[0])
    t("la fenetre suivante est toleree",
      totp.verifier(secret, totp.code(secret, T + totp.PAS), T)[0])
    t("deux fenetres avant sont refusees",
      not totp.verifier(secret, totp.code(secret, T - 2 * totp.PAS), T)[0])
    t("deux fenetres apres sont refusees",
      not totp.verifier(secret, totp.code(secret, T + 2 * totp.PAS), T)[0])

    bon, compteur = totp.verifier(secret, totp.code(secret, T), T, set())
    t("un compteur est renvoye", bon and compteur == T // totp.PAS, compteur)
    t("le meme code rejoue est refuse",
      not totp.verifier(secret, totp.code(secret, T), T, {compteur})[0])
    t("une AUTRE fenetre reste acceptee malgre le rejeu de la premiere",
      totp.verifier(secret, totp.code(secret, T + totp.PAS), T, {compteur})[0])

    t("un code trop court est refuse", not totp.verifier(secret, "123", T)[0])
    t("un code non numerique est refuse", not totp.verifier(secret, "abcdef", T)[0])
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
