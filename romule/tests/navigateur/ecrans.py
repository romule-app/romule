"""Les ecrans de l'interface, en un seul endroit.

Deux tests balayent le DOM rendu — les phrases restees en francais, et les
elements cliquables devenus inertes. Ni l'un ni l'autre ne voit ce qui n'est
pas AFFICHE : il faut donc ouvrir les ecrans un par un.

Cette liste etait dupliquee dans le premier de ces tests. La sortir ici n'est
pas du rangement : un ecran ajoute a l'interface doit etre ajoute a UN seul
endroit, sinon le second test continuera silencieusement de ne pas le voir —
ce qui est exactement le defaut que la phase 3.5 a corrige.
"""

import time

# Chaque entree ouvre un ecran. L'ordre compte : certaines dependent de la
# precedente (fermer la fiche avant d'ouvrir l'assistant).
ETAPES = [
    "app.tab('jeux')",
    "app.tab('settings')",
    "app.voirEntretien('doublons')",
    "app.voirEntretien('integrite')",
    "app.voirEntretien('acces')",
    "app.auditer(true)",
    "app.toggleJournal()",
    "app.toggleDrop(true)",
    # Les sections de reglages sont exclusives : chacune doit etre ouverte.
    "document.querySelector(\"#setnav a[href='#sec-console']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-biblio']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-entretien']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-acces']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-interface']\").click()",
    # Le navigateur de dossiers du serveur.
    "app.tab('settings'); app.ludoOuvrir()",
    # La fiche d'un jeu : l'ecran le plus dense.
    "app.tab('jeux'); (function(){const c=document.querySelector('#lib .gcard');"
    "if (c) app.openGame(c.dataset.key);})()",
    "app.closeGame(); app.openOnboard && app.openOnboard()",
    "app.closeOnboard && app.closeOnboard()",
]


def parcourir(n, releve, pause=0.9):
    """Ouvre chaque ecran et applique `releve` (une expression JS) a chacun.

    Rend la reunion de tout ce que `releve` a rapporte. Une etape qui echoue
    est ignoree : un ecran indisponible dans l'etat courant ne doit pas faire
    tomber le balayage des autres.
    """
    vu = set()
    for code in ETAPES:
        try:
            n.js(code)
        except Exception:
            pass
        time.sleep(pause)
        vu |= set(n.js(releve) or [])
    return vu
