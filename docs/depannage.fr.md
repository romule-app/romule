# Dépannage

## `docker compose up` fonctionne mais la page est refusée

C'est attendu au premier démarrage. Le conteneur est joignable mais n'a encore
aucun compte : Romule engendre donc un jeton.

```sh
docker compose logs romule
```

Ouvre l'adresse affichée, jeton compris. Voir
[le jeton de premier accès](securite.md).

## Romule refuse le dossier que j'ai choisi

Il refuse les emplacements manifestement faux — la racine du disque, ton
dossier personnel, un dépôt de code, tout ce qui est en lecture seule — parce
qu'il y déplace des fichiers et y crée des dossiers. Choisis un dossier qui ne
contient que tes jeux.

La même règle vaut pour `ROMULE_ROOT` au démarrage, et là le service s'arrête
plutôt que d'écrire au mauvais endroit.

## Le sélecteur dit « hors des dossiers autorisés »

`ROMULE_BASES` est renseigné et le chemin est en dehors. Sous Docker, cela veut
presque toujours dire que le dossier n'est pas monté du tout : ajoute-le à
`volumes:`. Rien de ce que fait l'interface n'atteint un chemin que le
conteneur ne voit pas.

## L'analyse ne trouve rien

Vérifie que le chemin affiché dans l'assistant est celui que tu attends. Romule
parcourt une arborescence, donc les jeux peuvent être dans des sous-dossiers,
mais la racine doit être la bonne. Les fichiers dont il ne reconnaît pas
l'extension sont ignorés — l'assistant dit combien d'extensions il connaît.

## Les jaquettes restent vides

La source par défaut travaille à partir des seuls title ID Switch : les autres
plateformes ont donc besoin d'une clé. **Réglages → Jaquettes et fiches**, puis
**Enregistrer et tester**. Si le test échoue, la clé est mauvaise — le message
dit quel service a refusé.

Les jaquettes ont deux sources, essayées dans cet ordre. SteamGridDB est une
base de *visuels* communautaires, pauvre sur les catalogues de consoles
portables ; IGDB est une base de jeux, et elle publie aussi des jaquettes —
Romule s'y rabat quand la première ne rend aucune image. **Renseigner les
identifiants IGDB corrige donc des jaquettes vides qu'une clé SteamGridDB seule
ne corrige pas.**

Encore faut-il que la source reconnaisse le jeu : un candidat doit couvrir les
deux tiers des mots distinctifs du titre. Un fichier nommé `Un Jeu (Europe)
(En,Fr) [!].nds` est cherché sous `Un Jeu` — la région et les marques de dump
sont retirées d'abord. Une jaquette appartenant à un autre jeu serait pire que
pas de jaquette du tout.

## Les `.nsz` / `.xcz` ne se convertissent pas

Ils demandent l'outil `nsz` **et** `prod.keys` :

```sh
pipx install nsz                          # Debian/Ubuntu
brew install pipx && pipx install nsz     # macOS
```

Puis pointe `ROMULE_KEYS` sur ton fichier de clés, ou monte-le en
`/keys/prod.keys` sous Docker. Romule ne fournit ni les clés de l'outil, ni
aucun moyen de se les procurer.

## La console n'est pas détectée

1. `adb` est-il installé ? Romule le dit sur l'écran principal sinon.
2. Le débogage USB (ou sans fil) est-il activé sur la console ?
3. As-tu accepté la demande d'autorisation affichée sur son écran ?
4. Sous Docker en réseau *bridge*, l'USB n'est pas visible. Utilise
   l'appairage Wi-Fi, ou voir [Installation](installation.md#reseau).

## Les transferts Wi-Fi sont lents

Deux à cinq fois plus lents que l'USB, par nature. Pour un premier transfert en
masse, le câble vaut le détour.

## Derrière un proxy inverse, tout le monde partage la même session

Renseigne `ROMULE_TRUSTED_PROXIES` — voir
[le piège du proxy inverse](securite.md). Sans lui, toutes les requêtes
paraissent venir du proxy.

## L'interface est en anglais

**Réglages → Interface → Langue**, ou pose `ui_lang` à `fr`. L'anglais est la
langue par défaut ; le français est livré à côté.

## Autre chose

- `python3 -m romule.audit` — rend compte de la configuration réellement en
  service.
- Le panneau **Journal**, sur la droite, contient ce que Romule a fait et
  pourquoi il a échoué.
- `_romule-lib.log`, dans le dossier de données du service (`ROMULE_ROOT`,
  ou le volume `/data`), contient la même chose, gardée
  d'un redémarrage à l'autre.

Pour ouvrir un ticket, indique la version (pied de l'interface, ou
`python3 -m romule --version`), si tu tournes sous Docker ou en direct, et ce
que tu attendais.
