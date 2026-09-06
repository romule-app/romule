"""A QR code, drawn with nothing but the standard library.

Why this file exists
--------------------
Setting up two-factor authentication meant reading a thirty-two character key
off the screen and typing it into a phone. Every authenticator app in existence
scans a QR code instead; the address to encode — `otpauth://…` — Romule already
builds.

Why it is written here rather than installed
--------------------------------------------
Romule has no runtime dependency, on purpose: it is a single `python3 -m
romule` away from running, on a NAS, in a container, on a laptop. Adding a
package for one image would be the first crack in that.

What it does, and does not
--------------------------
Byte mode, error correction level M, versions 1 to 10. That covers an
`otpauth://` address — about 145 characters, so version 8 — with room to spare.
Nothing else is needed here, and a general-purpose encoder would be more code
to be wrong in.

How we know it is right
-----------------------
This is the uncomfortable part: a QR code that is subtly wrong looks perfectly
fine and simply does not scan. So `test_qr.py` does not trust this file. It
reads the matrix BACK — finds the format information, undoes the mask, walks
the same zigzag, de-interleaves the blocks and returns the payload — and it
checks the Reed-Solomon syndromes of every block, which is an independent
computation from the polynomial division that produced them.

That catches placement, masking, interleaving, padding and the ECC arithmetic.
It cannot catch a shared misreading of the specification: the final proof is a
phone, once.
"""

# --------------------------------------------------------------- GF(256)
# The field the Reed-Solomon codes live in, with the primitive polynomial the
# QR specification fixes: x^8 + x^4 + x^3 + x^2 + 1.
_EXP = [0] * 512
_LOG = [0] * 256


def _build_tables():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_build_tables()


def _mul(a, b):
    if not a or not b:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _generator(n):
    """The generator polynomial for `n` error-correction codewords."""
    g = [1]
    for i in range(n):
        g = _poly_mul(g, [1, _EXP[i]])
    return g


def _poly_mul(a, b):
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] ^= _mul(x, y)
    return out


def ec_codewords(data, n):
    """The `n` error-correction codewords for these data codewords."""
    g = _generator(n)
    reste = list(data) + [0] * n
    for i in range(len(data)):
        coef = reste[i]
        if coef:
            for j, gc in enumerate(g):
                reste[i + j] ^= _mul(gc, coef)
    return reste[len(data):]


# ------------------------------------------------------- version tables
# Level M only: (ec per block, blocks in group 1, data per block in group 1,
# blocks in group 2, data per block in group 2).
_BLOCS = {
    1: (10, 1, 16, 0, 0),
    2: (16, 1, 28, 0, 0),
    3: (26, 1, 44, 0, 0),
    4: (18, 2, 32, 0, 0),
    5: (24, 2, 43, 0, 0),
    6: (16, 4, 27, 0, 0),
    7: (18, 4, 31, 0, 0),
    8: (22, 2, 38, 2, 39),
    9: (22, 3, 36, 2, 37),
    10: (26, 4, 43, 1, 44),
}

# Where the alignment patterns are centred, per version.
_ALIGNEMENTS = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

MAX_VERSION = 10


def _data_codewords(version):
    _, b1, d1, b2, d2 = _BLOCS[version]
    return b1 * d1 + b2 * d2


def _capacite(version):
    """How many bytes of payload fit, header and terminator included."""
    entete = 4 + (16 if version >= 10 else 8)
    return (_data_codewords(version) * 8 - entete) // 8


def choisir_version(n):
    """The smallest version that holds `n` bytes, or None."""
    for v in range(1, MAX_VERSION + 1):
        if _capacite(v) >= n:
            return v
    return None


# ----------------------------------------------------------- bit stream
class _Bits:
    def __init__(self):
        self.bits = []

    def add(self, valeur, longueur):
        for i in range(longueur - 1, -1, -1):
            self.bits.append((valeur >> i) & 1)

    def octets(self):
        return [int("".join(str(b) for b in self.bits[i:i + 8]).ljust(8, "0"), 2)
                for i in range(0, len(self.bits), 8)]


def _flux(donnees, version):
    """The data codewords: header, payload, terminator, padding."""
    b = _Bits()
    b.add(0b0100, 4)                                   # byte mode
    b.add(len(donnees), 16 if version >= 10 else 8)
    for octet in donnees:
        b.add(octet, 8)
    total = _data_codewords(version) * 8
    b.add(0, min(4, total - len(b.bits)))              # terminator
    while len(b.bits) % 8:
        b.bits.append(0)
    mots = b.octets()
    # The two padding bytes the specification fixes, alternating.
    for i in range(_data_codewords(version) - len(mots)):
        mots.append(0xEC if i % 2 == 0 else 0x11)
    return mots


def _entrelacer(mots, version):
    """Data and error-correction codewords, interleaved as the standard says."""
    nec, b1, d1, b2, d2 = _BLOCS[version]
    blocs, i = [], 0
    for _ in range(b1):
        blocs.append(mots[i:i + d1]); i += d1
    for _ in range(b2):
        blocs.append(mots[i:i + d2]); i += d2
    ecs = [ec_codewords(bl, nec) for bl in blocs]
    sortie = []
    for j in range(max(len(bl) for bl in blocs)):
        for bl in blocs:
            if j < len(bl):
                sortie.append(bl[j])
    for j in range(nec):
        for e in ecs:
            sortie.append(e[j])
    return sortie


# --------------------------------------------------------------- matrix
def _bch(valeur, generateur, bits):
    """The BCH remainder used by the format and version information."""
    d = valeur
    for _ in range(bits):
        if d >> (bits + generateur.bit_length() - 2) & 1:
            pass
    # Written the plain way: shift and reduce while the degree is high enough.
    d = valeur << (generateur.bit_length() - 1)
    while d.bit_length() >= generateur.bit_length():
        d ^= generateur << (d.bit_length() - generateur.bit_length())
    return d


def format_bits(masque, niveau=0b00):
    """The fifteen bits of format information, for level M and this mask."""
    v = (niveau << 3) | masque
    return ((v << 10) | _bch(v, 0b10100110111, 10)) ^ 0b101010000010010


def version_bits(version):
    """The eighteen bits of version information (versions 7 and above)."""
    return (version << 12) | _bch(version, 0b1111100100, 12)


def _reserve(taille, version):
    """True where a module belongs to a pattern, not to the data."""
    r = [[False] * taille for _ in range(taille)]

    def bloc(x, y, w, h):
        for j in range(y, y + h):
            for i in range(x, x + w):
                if 0 <= i < taille and 0 <= j < taille:
                    r[j][i] = True

    # The three corners, SEPARATORS AND FORMAT AREA INCLUDED. Written as a 9x9
    # centred on the finder, the block ran from -1 and therefore stopped at row
    # and column 7 — leaving row 8 and column 8, which carry the format
    # information, free for data. Thirty-one modules were written twice.
    bloc(0, 0, 9, 9)
    bloc(taille - 8, 0, 8, 9)
    bloc(0, taille - 8, 9, 8)
    bloc(6, 0, 1, taille)
    bloc(0, 6, taille, 1)
    for cy in _ALIGNEMENTS[version]:
        for cx in _ALIGNEMENTS[version]:
            if (cx < 8 and cy < 8) or (cx < 8 and cy > taille - 9) \
                    or (cx > taille - 9 and cy < 8):
                continue
            bloc(cx - 2, cy - 2, 5, 5)
    if version >= 7:
        bloc(taille - 11, 0, 3, 6)
        bloc(0, taille - 11, 6, 3)
    return r


def _motifs(m, taille, version):
    """Finder patterns, separators, timing, alignment, and the dark module."""
    def finder(x, y):
        for j in range(-1, 8):
            for i in range(-1, 8):
                if not (0 <= x + i < taille and 0 <= y + j < taille):
                    continue
                bord = i in (0, 6) and 0 <= j <= 6
                haut = j in (0, 6) and 0 <= i <= 6
                coeur = 2 <= i <= 4 and 2 <= j <= 4
                m[y + j][x + i] = 1 if (bord or haut or coeur) else 0

    finder(0, 0)
    finder(taille - 7, 0)
    finder(0, taille - 7)
    for i in range(taille):
        if m[6][i] is None:
            m[6][i] = 1 - (i % 2)
        if m[i][6] is None:
            m[i][6] = 1 - (i % 2)
    for cy in _ALIGNEMENTS[version]:
        for cx in _ALIGNEMENTS[version]:
            if (cx < 8 and cy < 8) or (cx < 8 and cy > taille - 9) \
                    or (cx > taille - 9 and cy < 8):
                continue
            for j in range(-2, 3):
                for i in range(-2, 3):
                    m[cy + j][cx + i] = 1 if (max(abs(i), abs(j)) != 1) else 0
    m[taille - 8][8] = 1                      # the dark module, always set


def _placer_format(m, taille, masque):
    bits = format_bits(masque)
    for i in range(15):
        b = (bits >> i) & 1
        if i < 6:
            m[i][8] = b
        elif i == 6:
            m[7][8] = b
        elif i == 7:
            m[8][8] = b
        elif i == 8:
            m[8][7] = b
        else:
            m[8][14 - i] = b
        # The second copy: column 8 from the bottom, then row 8 from the
        # right. Written transposed, the two copies of the format information
        # disagreed — and a reader that trusts either one gets a mask number
        # that is not the one the data was masked with.
        # SEVEN bits in the column, then eight in the row. Written as eight
        # and seven, the last one landed on the dark module at
        # (taille - 8, 8) — a module the standard fixes at 1, and which a
        # reader uses to orient itself.
        if i < 7:
            m[taille - 1 - i][8] = b
        else:
            m[8][taille - 15 + i] = b


def _placer_version(m, taille, version):
    if version < 7:
        return
    bits = version_bits(version)
    for i in range(18):
        b = (bits >> i) & 1
        a, c = i // 3, i % 3
        m[a][taille - 11 + c] = b
        m[taille - 11 + c][a] = b


def _zigzag(taille):
    """The order the data modules are written in: column pairs, right to left."""
    ordre = []
    col = taille - 1
    montant = True
    while col > 0:
        if col == 6:                      # the vertical timing column is skipped
            col -= 1
        lignes = range(taille - 1, -1, -1) if montant else range(taille)
        for ligne in lignes:
            for dx in (0, 1):
                ordre.append((col - dx, ligne))
        col -= 2
        montant = not montant
    return ordre


def _masque(i, x, y):
    return (
        (x + y) % 2 == 0,
        y % 2 == 0,
        x % 3 == 0,
        (x + y) % 3 == 0,
        (y // 2 + x // 3) % 2 == 0,
        (x * y) % 2 + (x * y) % 3 == 0,
        ((x * y) % 2 + (x * y) % 3) % 2 == 0,
        ((x + y) % 2 + (x * y) % 3) % 2 == 0,
    )[i]


def _penalite(m, taille):
    """The score the standard uses to pick a mask: lower is better."""
    total = 0
    for bande in (m, [list(c) for c in zip(*m, strict=True)]):
        for ligne in bande:
            n, prec = 1, ligne[0]
            for v in ligne[1:]:
                if v == prec:
                    n += 1
                else:
                    if n >= 5:
                        total += 3 + (n - 5)
                    n, prec = 1, v
            if n >= 5:
                total += 3 + (n - 5)
    for y in range(taille - 1):
        for x in range(taille - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                total += 3
    motif = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    for bande in (m, [list(c) for c in zip(*m, strict=True)]):
        for ligne in bande:
            for i in range(len(ligne) - 10):
                if ligne[i:i + 11] == motif or ligne[i:i + 11] == motif[::-1]:
                    total += 40
    sombres = sum(sum(l) for l in m)
    pct = sombres * 100 // (taille * taille)
    total += 10 * (abs(pct - 50) // 5)
    return total


def matrice(texte):
    """The QR modules for this text: a list of rows of 0/1."""
    donnees = texte.encode("utf-8")
    version = choisir_version(len(donnees))
    if version is None:
        raise ValueError("texte trop long pour un QR de version %d" % MAX_VERSION)
    mots = _entrelacer(_flux(donnees, version), version)
    taille = 17 + 4 * version
    reserve = _reserve(taille, version)
    ordre = [(x, y) for (x, y) in _zigzag(taille) if not reserve[y][x]]

    meilleur, score = None, None
    for masque in range(8):
        m = [[None] * taille for _ in range(taille)]
        _motifs(m, taille, version)
        _placer_version(m, taille, version)
        _placer_format(m, taille, masque)
        bits = [(o >> (7 - i)) & 1 for o in mots for i in range(8)]
        for (x, y), b in zip(ordre, bits, strict=False):
            m[y][x] = b ^ (1 if _masque(masque, x, y) else 0)
        for (x, y) in ordre[len(bits):]:
            m[y][x] = 1 if _masque(masque, x, y) else 0
        plein = [[0 if v is None else v for v in ligne] for ligne in m]
        p = _penalite(plein, taille)
        if score is None or p < score:
            meilleur, score = plein, p
    return meilleur


def svg(texte, module=4, marge=4):
    """The QR code as an inline SVG, ready for `img src="data:"` or innerHTML.

    A `data:` URI rather than a route: the address encoded here is a SECRET
    being set up, and a route serving it would be one more place it exists.
    """
    m = matrice(texte)
    n = len(m)
    cote = (n + 2 * marge) * module
    carres = []
    for y, ligne in enumerate(m):
        x = 0
        while x < n:
            if ligne[x]:
                large = 1
                while x + large < n and ligne[x + large]:
                    large += 1
                carres.append('<rect x="%d" y="%d" width="%d" height="%d"/>'
                              % ((x + marge) * module, (y + marge) * module,
                                 large * module, module))
                x += large
            else:
                x += 1
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'shape-rendering="crispEdges" role="img">'
            '<rect width="%d" height="%d" fill="#ffffff"/>'
            '<g fill="#000000">%s</g></svg>'
            % (cote, cote, cote, cote, "".join(carres)))
