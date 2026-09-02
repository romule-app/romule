# Stockage : pourquoi il n'y a pas de base de données

Romule range son état dans des fichiers JSON, et reconstruit l'inventaire à
partir du système de fichiers à la demande. C'est un choix, et il revient assez
souvent — d'ordinaire sous la forme *« ça ne devrait pas être dans SQLite ? »* —
pour que la réponse mérite d'être écrite, avec les mesures qui l'ont produite.

## La réponse courte

**Une base de données n'aurait pas corrigé ce qui était réellement lent.** Le
coût n'a jamais été de lire des données. Il était de construire des objets
`pathlib.Path` par milliers, à chaque affichage, pour les jeter aussitôt.

## Ce qui a été mesuré

Une ludothèque synthétique de **20 000 titres / 39 525 fichiers**, caches
chauds — c'est-à-dire le cas qu'une base est censée aider. `/api/scan` est la
requête que paie chaque affichage.

| | Avant | Après | |
|---|---|---|---|
| `/api/scan`, à chaud | 1 759 ms | **1 170 ms** | −33 % |
| Démarrage (import + premier inventaire) | 949 ms | **457 ms** | −52 % |

Le profil d'avant, sur les 1 887 ms passées dans l'inventaire :

| Quoi | Temps | Part |
|---|---|---|
| `Path.relative_to` | 744 ms | 39 % |
| `sorted()` sur des objets `Path` | 362 ms | 19 % — 504 724 comparaisons |
| `stat` | 138 ms | appelé **deux fois** par fichier |
| Sérialisation JSON | — | n'apparaissait pas dans les 18 premières |

Cette dernière ligne est tout l'argument. Si sérialiser la réponse ne se voit
même pas, le goulot n'est pas le stockage, et aucun moteur de stockage ne peut
le déplacer.

## Ce qu'a été la correction

Des chaînes et `os.walk` à la place de `pathlib`, dans la seule boucle qui
tourne par fichier et par requête :

- `os.walk` élague les dossiers ignorés en place, au lieu de descendre dans
  `_corbeille/` pour rejeter ensuite chaque fichier ;
- le tri porte sur `os.path.normcase(chemin)`, ce qui reproduit exactement
  `sorted(rglob("*"))` — `PurePath.__lt__` compare cette même chaîne
  normalisée ;
- `os.scandir` (dans `os.walk`) connaît déjà le type du fichier : le second
  `stat` disparaît ;
- `splitext` est calculé une fois et porté, pas recalculé ;
- `titleid.pretty_name` ne construit plus un `Path` pour lire `.stem`.

La réécriture a été vérifiée en rejouant **l'ancienne boucle telle quelle** sur
la même ludothèque, puis en comparant chaque champ de chaque entrée : 4 433
fichiers, zéro écart, y compris sur les cas que la ludothèque synthétique ne
produit pas d'elle-même — un fichier à la racine, un dossier ignoré, des
accents, une extension en majuscules, une arborescence profonde. Une réécriture
de performance qui change sa sortie en silence est exactement le défaut que ce
projet passe son temps à trouver.

## Là où SQLite n'aiderait toujours pas

L'inventaire est **déduit, pas rangé**. La source de vérité de Romule est ton
dossier de jeux : tu peux y déposer un fichier depuis le Finder, et l'analyse
suivante le voit. Une base devrait de toute façon être réconciliée avec le
système de fichiers à chaque requête — donc faire le parcours **et** interroger
la base.

Le reste de l'état est petit et rarement écrit :

| Fichier | Taille typique | Écrit |
|---|---|---|
| `_romule-config.json` | ~1 Kio | quand un réglage change |
| `_romule-comptes.json` | ~400 o | quand un compte change |
| `_romule-cles.json` | ~1 Kio | à la création ou à la révocation d'une clé |
| `_covers/` | un fichier par jeu | quand une jaquette est récupérée |

Réécrire le fichier entier coûte O(n) par écriture, ce qui compte à dix mille
lignes et pas à dix. Le remplacement atomique (`os.replace`) donne déjà la
résistance aux plantages — la propriété pour laquelle on adopte d'ordinaire une
base.

## Là où elle aiderait, honnêtement

Trois cas, dont Romule n'est aujourd'hui dans aucun :

1. **Plusieurs écrivains.** Un processus, un verrou par fichier. Un second
   Romule pointé sur le même dossier corromprait l'état — mais ce serait aussi
   le cas de la plupart des outils auto-hébergés.
2. **Des requêtes qui ne sont pas « donne-moi tout ».** Tout finit aujourd'hui
   dans le navigateur, qui filtre en mémoire en moins de 16 ms. Une recherche
   côté serveur sur des centaines de milliers de titres voudrait un index.
3. **L'historique.** Romule ne garde aucune chronologie — ni « quand ce jeu
   a-t-il été importé », ni journal par jeu. En ajouter un voudrait une table,
   pas un fichier JSON qui grossit sans fin.

Si l'un de ces cas arrive, la conclusion change. D'ici là, ajouter une base
voudrait dire un schéma, des migrations et une seconde source de vérité à tenir
d'accord avec le système de fichiers — en échange d'un goulot qui se trouvait
ailleurs.

!!! note "La règle du zéro dépendance n'est pas la raison"
    `sqlite3` est livré avec Python : l'employer n'enfreindrait aucune règle.
    La raison est qu'il n'aurait pas aidé, et c'est la mesure qui le dit.

## Refaire la mesure

```sh
python3 outils/mesurer-perf.py --titres 20000
```

Les seuils sont dans l'outil, et l'intégration continue avertit quand l'un est
franchi. Si tu rends ceci plus rapide, c'est ce nombre-là qu'il faut bouger.
