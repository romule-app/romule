# Contribuer

Le guide complet vit dans
[CONTRIBUTING.md](https://github.com/romule-app/romule/blob/main/CONTRIBUTING.md).
En résumé :

## Deux règles non négociables

**Zéro dépendance d'exécution.** Romule tourne sur la seule bibliothèque
standard de Python, et un job d'intégration continue bloquant échoue si un
import hors stdlib apparaît. Les binaires externes (`adb`, `nsz`, `unar`, `7z`)
sont facultatifs : l'absence de l'un désactive une fonction, jamais le
démarrage.

**Aucune donnée personnelle, aucune donnée de jeu, aucune clé.**
`outils/verifier-fuite.py` refuse les clés de console, les ROMs, les images de
jaquette, les fichiers d'état, les identifiants et les adresses IP privées dans
l'index git.

## Lancer les contrôles

```sh
python3 lancer_tests.py --navigateur   # les cinq familles
python3 outils/verifier-fuite.py       # contrôle de fuite
python3 -m romule.audit                # 0 grave, 0 alerte attendus
```

La famille navigateur pilote un vrai Chrome sans affichage et attrape ce que la
lecture du CSS ne peut pas voir : débordement, contrôles recouverts par
d'autres, phrases non traduites. Si tu touches à l'interface, lance-la.

## Ajouter une traduction

Copie `romule/locales/fr.json` en `xx.json`, garde les clés françaises, traduis
les valeurs, et pose `_meta.langue` au nom de la langue dans sa propre langue.
Elle apparaît toute seule dans le sélecteur.

!!! warning "N'assemble jamais une phrase à partir de morceaux"
    `'Trouvé ' + n + ' jeux'` produit trois clés qu'aucun catalogue ne peut
    tenir. Utilise `phrase('%d {jeu|jeux} trouvé', n)`, ou `nb(n, '{jeu|jeux}')`
    pour un simple décompte. Cette erreur a déjà caché 49 phrases au contrôle de
    traduction.

!!! tip "Les pluriels s'écrivent `{singulier|pluriel}`"
    `1 fichier(s)` n'est pas un pluriel, c'est un aveu. Les deux formes vont
    dans la chaîne — `nb(n, '{fichier|fichiers}')` — et le catalogue en choisit
    une **par langue**, car les règles diffèrent : le français écrit
    *0 fichier* au singulier, l'anglais écrit *0 files* au pluriel. Une règle
    unique remplacerait une faute par une autre.

## Ajouter un profil d'émulateur

Dépose un fichier JSON dans `romule/profils/`, sur le modèle d'`eden.json`.
Pose `"verifie": false` à moins de l'avoir éprouvé face à du matériel réel —
l'interface étiquette les profils non vérifiés, et cette étiquette est le
défaut honnête.

## Style de la maison

Les commentaires et les docstrings sont **en anglais**, comme tout ce que le
dépôt montre. `outils/verifier-anglais.py` y refuse la prose française et la CI
le lance ; une ligne qui *cite* volontairement du français porte `anglais:ok`
avec sa raison à côté. Les chaînes d'interface, elles, restent en français —
ce sont les clés du catalogue i18n, un mécanisme et non un style.

Un commentaire dit *pourquoi*, jamais *quoi* : s'il redit la ligne d'en dessous,
supprime-le. Ceux qui valent la peine expliquent une contrainte invisible dans
le code — une règle qui en combat une autre, une valeur mesurée, un bogue qu'une
réécriture naïve ramènerait.
