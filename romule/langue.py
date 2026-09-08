"""The language the TERMINAL speaks.

The interface has had two languages since the beginning; the terminal had one,
and it was French. That is not a small inconsistency: `ui_lang` defaults to
`en` — "the language of a public self-hosted project", as `config.py` puts it —
so the ordinary installation showed an English interface and wrote French to
`docker logs`. Whoever reads those logs is precisely the person who cannot open
the interface.

The catalogues are the ones the browser already uses, `locales/*.json`: one
translation, one place, whichever surface displays it. The French sentence is
the key here as it is there.

Interpolation happens AFTER the lookup, never before. `"Ludothèque : %s" % path`
produces a string no catalogue can hold, so call sites keep the template:

    console.say(langue.t(messages.LUDO) % config.LUDO)

Nothing here raises. A missing catalogue, a broken file, a sentence nobody has
translated: the French is written and the service starts. A log line is not
worth a crash.
"""

import json
import os
import threading
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "locales"

# `fr` has no catalogue to load: the keys ARE French.
DEFAUT = "en"

_VERROU = threading.Lock()
_code = ""
_table = {}


def _lire(code):
    try:
        d = json.loads((DOSSIER / ("%s.json" % code)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, str)}


def choisir(code):
    """Set the terminal's language. Unknown or empty falls back to the default."""
    global _code, _table
    code = (code or "").strip().lower()[:8]
    if not code or not (DOSSIER / ("%s.json" % code)).is_file():
        code = DEFAUT
    with _VERROU:
        if code == _code:
            return _code
        _code = code
        _table = {} if code == "fr" else _lire(code)
    return _code


def actuelle():
    return _code or choisir(os.environ.get("ROMULE_LANG", ""))


def t(phrase):
    """The sentence in the terminal's language, or the sentence itself."""
    if not _code:
        actuelle()
    return _table.get(phrase, phrase)


class Phrase:
    """A template and its values, kept APART until the last moment.

    `"%d fichier(s) rangé(s) dans %s" % (n, dossier)` produces a string no
    catalogue can hold, so a sentence with values in it cannot be translated
    once it has been assembled. Assembling it late is the whole point.

    It matters more than it looks. The same sentence goes to three places:

      * the terminal, which must speak the operator's language;
      * the browser's journal, which translates client-side and therefore needs
        the FRENCH key;
      * the log file, which is read alongside the browser.

    Translating at the call site would have sent English to all three, and the
    browser — whose catalogue is keyed on French — would have had nothing to
    look up. So `str()` gives the French, and only `console` asks for the
    translation.
    """

    __slots__ = ("modele", "valeurs")

    def __init__(self, modele, *valeurs):
        self.modele = modele
        self.valeurs = valeurs

    def __str__(self):
        return (self.modele % self.valeurs) if self.valeurs else self.modele

    def traduite(self):
        modele = t(self.modele)
        try:
            return (modele % self.valeurs) if self.valeurs else modele
        except (TypeError, ValueError):
            # A translation whose placeholders do not match the original must
            # not take a log line down with it: the French still says it.
            return str(self)


def phrase(modele, *valeurs):
    return Phrase(modele, *valeurs)
