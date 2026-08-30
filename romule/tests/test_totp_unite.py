"""Tolerance d'horloge du second facteur, verifiee sans reseau ni horloge reelle.

Ces assertions vivaient dans le parcours HTTP, ou elles etaient condamnees a
etre instables : le test y demandait « le code d'il y a 30 secondes » sans
pouvoir savoir si cette fenetre-la avait deja servi. Quand une frontiere de
fenetre tombait entre la connexion et le controle — une fois sur cinq environ —
le code designait une fenetre consommee, le serveur le refusait comme un rejeu,
et l'echec ressemblait a un bug de tolerance.

Ici `moment` est fourni, donc rien ne bouge sous les pieds du test.
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
    # Un instant fixe, aligne sur une fenetre : aucune frontiere ne peut etre
    # franchie pendant le test.
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
