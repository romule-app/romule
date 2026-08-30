"""EmuReady (beta) : reglages recommandes par la communaute, par jeu et par appareil.

https://www.emuready.com — plateforme ouverte de rapports de compatibilite.
On utilise uniquement des endpoints publics, en lecture, avec un cache local
pour ne pas solliciter leur service inutilement.

L'appariement d'un jeu se fait a trois niveaux, jamais a l'aveugle :
  confirme  le title ID renvoye par EmuReady est identique au notre
  probable  jeu trouve par son nom officiel, sans confirmation possible
  absent    rien dans leur base
"""

import json
import re
import time
import urllib.parse
import urllib.request

from . import config, meta

BASE = "https://www.emuready.com/api/mobile/trpc"
CACHE = config.ROOT / "_emuready-cache.json"
CACHE_TTL = 7 * 24 * 3600          # une semaine : ces donnees bougent lentement

# Echelle de performance d'EmuReady (rang 1 = le mieux).
RANGS = {"Perfect": 1, "Great": 2, "Playable": 3, "Poor": 4,
         "Ingame": 5, "Intro": 6, "Loadable": 7, "Nothing": 8}
# Regroupement lisible pour l'interface.
NIVEAUX = {1: ("parfait", "Parfait"), 2: ("parfait", "Très bon"),
           3: ("jouable", "Jouable"), 4: ("limite", "Problèmes"),
           5: ("limite", "Problèmes"), 6: ("limite", "Ne démarre pas"),
           7: ("limite", "Ne démarre pas"), 8: ("limite", "Ne démarre pas")}

_TM = re.compile(r"[™®©]")


def clean_title(nom):
    """Nom exploitable pour la recherche : sans marques deposees ni parasites."""
    n = _TM.sub("", nom or "")
    n = re.sub(r"\s*[\[\(][^\])]*[\])]", " ", n)
    return re.sub(r"\s{2,}", " ", n).strip(" .-")


# --------------------------------------------------------------------- appel

def call(route, payload=None, timeout=25):
    url = "%s/%s" % (BASE, route)
    if payload is not None:
        url += "?input=" + urllib.parse.quote(json.dumps({"json": payload}))
    req = urllib.request.Request(url, headers={"User-Agent": "switchlib/emuready"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(d["error"]["json"].get("message", "erreur")[:200])
    return d["result"]["data"]["json"]


# --------------------------------------------------------------------- cache

def _load():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"jeux": {}, "appareils": [], "maj": 0}


def _save(c):
    try:
        CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def cached():
    return _load()


def clear():
    CACHE.unlink(missing_ok=True)


# ------------------------------------------------------------------ appareils

def devices(recherche="", force=False):
    """Appareils connus d'EmuReady (mis en cache)."""
    c = _load()
    if c["appareils"] and not force and (time.time() - c.get("maj", 0)) < CACHE_TTL:
        liste = c["appareils"]
    else:
        try:
            r = call("devices.get", {"limit": 500})
            liste = [{"id": d["id"],
                      "nom": ("%s %s" % ((d.get("brand") or {}).get("name", ""),
                                         d.get("modelName", ""))).strip()}
                     for d in (r.get("devices") or [])]
            c["appareils"] = liste
            c["maj"] = time.time()
            _save(c)
        except Exception:
            liste = c["appareils"]
    if recherche:
        q = recherche.lower()
        liste = [d for d in liste if q in d["nom"].lower()]
    return liste


def suggest_devices(modele):
    """Variantes plausibles pour un modele detecte (« AYN Thor » -> Thor Base/Lite/Pro/Max)."""
    mots = [m for m in re.split(r"\W+", clean_title(modele or "")) if len(m) > 2]
    if not mots:
        return []
    tous = devices()
    for m in reversed(mots):                    # le dernier mot est le plus discriminant
        hits = [d for d in tous if m.lower() in d["nom"].lower()]
        if hits:
            return sorted(hits, key=lambda d: d["nom"])
    return []


# ------------------------------------------------------------- correspondance

def match_game(tid, nom_fichier, cfg=None):
    """Retrouve un jeu sur EmuReady. Renvoie {id, titre, niveau_confiance}."""
    fiche = meta.fetch(tid, dict(cfg or {}, meta_lang="en")) or {}
    requete = clean_title(fiche.get("name") or nom_fichier)
    if not requete:
        return None
    try:
        res = call("games.get", {"search": requete, "limit": 5}) or {}
    except Exception:
        return None
    cands = res.get("games") or []
    if not cands:
        return None

    # niveau 1 : leur title ID confirme le notre
    for c in cands:
        try:
            r = call("games.getBestSwitchTitleId", {"gameName": c["title"]}) or {}
        except Exception:
            continue
        if (r.get("titleId") or "").lower() == (tid or "").lower():
            return {"id": c["id"], "titre": c["title"], "confiance": "confirme",
                    "requete": requete}

    # niveau 2 : meilleur candidat par similarite de nom, a faire valider
    cible = clean_title(requete).lower()
    meilleur = min(cands, key=lambda c: 0 if clean_title(c["title"]).lower() == cible else 1)
    exact = clean_title(meilleur["title"]).lower() == cible
    return {"id": meilleur["id"], "titre": meilleur["title"],
            "confiance": "probable" if exact else "incertain", "requete": requete}


# ------------------------------------------------------------------ rapports

def listings_for(game_id, device_id=None, emulateur="eden"):
    """Rapports d'un jeu, filtres sur l'emulateur et tries du meilleur au pire."""
    try:
        r = call("listings.byGame", {"gameId": game_id}) or {}
    except Exception:
        return []
    items = r if isinstance(r, list) else (r.get("listings") or [])
    out = []
    for x in items:
        emu = ((x.get("emulator") or {}).get("name") or "").lower()
        if emulateur and emu != emulateur:
            continue
        perf = (x.get("performance") or {})
        out.append({
            "id": x.get("id"),
            "appareil": (x.get("device") or {}).get("modelName") or "?",
            "appareil_id": x.get("deviceId"),
            "emulateur": (x.get("emulator") or {}).get("name") or "?",
            "note": perf.get("label") or "?",
            "rang": RANGS.get(perf.get("label"), 9),
            "notes": (x.get("notes") or "")[:400],
        })
    # priorite : mon appareil d'abord, puis la meilleure note
    out.sort(key=lambda l: (0 if (device_id and l["appareil_id"] == device_id) else 1,
                            l["rang"]))
    return out


def config_of(listing_id):
    """Contenu du fichier de configuration Eden d'un rapport."""
    r = call("listings.getEmulatorConfig", {"listingId": listing_id}) or {}
    if (r.get("type") or "").lower() != "eden":
        raise RuntimeError("ce rapport ne fournit pas de configuration Eden")
    return r.get("content") or ""


# ------------------------------------------------------------ synchronisation

def sync(jeux, cfg, job, force=False):
    """Met a jour l'etat de compatibilite des jeux de la ludotheque."""
    c = _load()
    device_id = (cfg.get("emuready_device") or "").strip() or None
    job.set_total(len(jeux))
    neufs = 0
    for g in jeux:
        if not job.checkpoint():
            job.log("Synchronisation interrompue.")
            break
        tid = (g.get("tid") or "").lower()
        if not tid:
            job.tick()
            continue
        vieux = c["jeux"].get(tid)
        frais = vieux and (time.time() - vieux.get("maj", 0)) < CACHE_TTL \
            and vieux.get("appareil") == device_id
        if frais and not force:
            job.tick()
            continue

        job.set_detail(g.get("name", "")[:48])
        m = match_game(tid, g.get("name"), cfg)
        entree = {"maj": time.time(), "appareil": device_id, "nom": g.get("name")}
        if not m:
            entree.update({"etat": "absent"})
        else:
            rapports = listings_for(m["id"], device_id)
            mien = [r for r in rapports if device_id and r["appareil_id"] == device_id]
            retenu = (mien or rapports or [None])[0]
            entree.update({
                "etat": "trouve" if retenu else "aucun_rapport",
                "jeu_id": m["id"], "titre": m["titre"], "confiance": m["confiance"],
                "rapports": rapports[:8],
                "meilleur": retenu,
                "pour_mon_appareil": bool(mien),
            })
            neufs += 1
        c["jeux"][tid] = entree
        _save(c)
        job.tick()
    job.set_detail("")
    job.log("Compatibilite mise a jour pour %d jeu(x)." % neufs)
    return c


def badge(tid):
    """Etat compact d'un jeu pour l'affichage : (classe, texte) ou None."""
    e = _load()["jeux"].get((tid or "").lower())
    if not e or e.get("etat") == "absent":
        return None
    best = e.get("meilleur")
    if not best:
        return ("inconnu", "Non testé")
    cls, txt = NIVEAUX.get(best["rang"], ("inconnu", best["note"]))
    if not e.get("pour_mon_appareil") and best.get("appareil"):
        # nommer la console testee plutot que dire « autre appareil », qui
        # laissait l'utilisateur deviner de quoi il s'agissait
        txt += " (sur %s)" % best["appareil"]
    return (cls, txt)
