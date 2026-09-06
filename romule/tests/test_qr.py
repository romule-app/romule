"""The QR code is read BACK, not taken on trust.

A QR code that is subtly wrong looks perfectly fine and simply does not scan.
There is no scanner here and no reference library to compare against — the
project has no runtime dependency and the offline cache holds none — so the
only honest check is to decode what was encoded, by a path that does not reuse
the encoder's own steps.

What the decoder does, and why each part matters:

  * it reads the FORMAT INFORMATION out of the matrix and recovers the mask
    from it. A wrong mask number, or format bits written in the wrong cells,
    produces a code every scanner refuses — and nothing else here would notice;
  * it undoes that mask and walks the same zigzag, which proves the data
    modules were placed where a reader expects them;
  * it de-interleaves the blocks and strips the header, which proves the block
    split, the padding and the character count;
  * and it checks the Reed-Solomon SYNDROMES of every codeword block. That is
    an independent computation: the encoder produced those bytes by polynomial
    division, and this evaluates the polynomial at the roots instead. A block
    whose syndromes are all zero is a block a real decoder would accept.

What it cannot catch is a shared misreading of the specification. The final
proof is a phone, once.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import qr                                             # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


def _masque_lu(m, taille):
    """The mask number, read out of the format information."""
    bits = 0
    for i in range(15):
        # The second copy: SEVEN bits up column 8 from the bottom, then eight
        # along row 8 from the right. The eighth cell of that column is the
        # dark module, not a format bit.
        if i < 7:
            b = m[taille - 1 - i][8]
        else:
            b = m[8][taille - 15 + i]
        bits |= b << i
    brut = bits ^ 0b101010000010010
    return (brut >> 10) & 0b111


def _syndromes_nuls(bloc, nec):
    """Does this codeword block satisfy its Reed-Solomon check?

    Evaluated at the roots — the encoder divided instead. Two different
    computations agreeing is what makes this worth writing.
    """
    for i in range(nec):
        s = 0
        for octet in bloc:
            s = qr._mul(s, qr._EXP[i]) ^ octet
        if s:
            return False
    return True


def decoder(m):
    """The text the matrix carries, read the way a scanner would."""
    taille = len(m)
    version = (taille - 17) // 4
    masque = _masque_lu(m, taille)
    reserve = qr._reserve(taille, version)
    ordre = [(x, y) for (x, y) in qr._zigzag(taille) if not reserve[y][x]]
    bits = [m[y][x] ^ (1 if qr._masque(masque, x, y) else 0) for (x, y) in ordre]
    mots = [int("".join(str(b) for b in bits[i:i + 8]), 2)
            for i in range(0, len(bits) - len(bits) % 8, 8)]

    nec, b1, d1, b2, d2 = qr._BLOCS[version]
    tailles = [d1] * b1 + [d2] * b2
    blocs = [[] for _ in tailles]
    i = 0
    for j in range(max(tailles)):
        for k, n in enumerate(tailles):
            if j < n:
                blocs[k].append(mots[i]); i += 1
    ecs = [[] for _ in tailles]
    for _ in range(nec):
        for k in range(len(tailles)):
            ecs[k].append(mots[i]); i += 1

    for bloc, ec in zip(blocs, ecs, strict=True):
        if not _syndromes_nuls(bloc + ec, nec):
            raise ValueError("syndromes non nuls : les codes correcteurs sont faux")

    plat = [b for bloc in blocs for b in bloc]
    flux = "".join(format(o, "08b") for o in plat)
    if flux[:4] != "0100":
        raise ValueError("mode inattendu : %s" % flux[:4])
    n_bits = 16 if version >= 10 else 8
    n = int(flux[4:4 + n_bits], 2)
    debut = 4 + n_bits
    octets = [int(flux[debut + 8 * k:debut + 8 * k + 8], 2) for k in range(n)]
    return bytes(octets).decode("utf-8")


def test_un_aller_retour_simple():
    texte = "otpauth://totp/Romule:moi@exemple.fr?secret=ABCDEFGH&issuer=Romule"
    t("un aller-retour rend le meme texte", decoder(qr.matrice(texte)) == texte)


def test_chaque_version_utile():
    """One payload per version, at the size that forces it."""
    rng = random.Random(1789)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:/?&=%."
    for v in range(1, qr.MAX_VERSION + 1):
        n = qr._capacite(v)
        texte = "".join(rng.choice(alphabet) for _ in range(n))
        m = qr.matrice(texte)
        attendu = 17 + 4 * v
        t("version %d : la matrice fait %d modules" % (v, attendu),
          len(m) == attendu, len(m))
        t("version %d : le texte revient intact" % v, decoder(m) == texte)


def test_la_longueur_reelle_dune_adresse_otpauth():
    """The one payload this file exists for, at its real length."""
    from romule import totp
    texte = totp.uri("LATA23MHTONB3LYZHTSHEMZS6JMHLKZC", "alex@example.org")
    t("une vraie adresse otpauth tient", qr.choisir_version(len(texte)) is not None,
      len(texte))
    t("et se relit sans perte", decoder(qr.matrice(texte)) == texte)


def test_les_motifs_obligatoires_sont_la():
    m = qr.matrice("x" * 40)
    taille = len(m)
    coins = [(0, 0), (taille - 7, 0), (0, taille - 7)]
    t("les trois motifs de reperage sont dessines",
      all(m[y + 3][x + 3] == 1 and m[y + 1][x + 1] == 0 for x, y in coins))
    t("la ligne de synchronisation alterne",
      all(m[6][i] == (1 - i % 2) for i in range(8, taille - 8)))
    # Always set, whatever the mask: a scanner uses it to orient itself.
    t("le module sombre est pose", m[taille - 8][8] == 1)


def test_un_texte_trop_long_est_refuse():
    """Silence would produce a code that scans to something truncated."""
    try:
        qr.matrice("x" * (qr._capacite(qr.MAX_VERSION) + 1))
        t("un texte trop long est refuse", False, "aucune exception")
    except ValueError:
        t("un texte trop long est refuse", True)


def test_le_svg_est_autonome():
    s = qr.svg("otpauth://totp/x?secret=y")
    t("le SVG ne reference aucun fichier", "http" not in s.replace(
        'xmlns="http://www.w3.org/2000/svg"', ""))
    t("il porte un fond blanc", 'fill="#ffffff"' in s)


for fn in (test_un_aller_retour_simple, test_chaque_version_utile,
           test_la_longueur_reelle_dune_adresse_otpauth,
           test_les_motifs_obligatoires_sont_la,
           test_un_texte_trop_long_est_refuse, test_le_svg_est_autonome):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
