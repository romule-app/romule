# Dépannage

## `docker compose up` fonctionne mais la page est refusée

Seulement si quelque chose la protège déjà. Sur une installation neuve, la page
s'ouvre : tant que tu n'as pas répondu à l'étape « Ton accès » de l'assistant,
le service répond à tout le monde — c'est ce qui rend l'assistant atteignable
depuis ton téléphone.

Si elle refuse, demande ce qui la garde :

```sh
docker compose exec romule python3 -m romule access status
```

Un compte ou un SSO : connecte-toi. Un jeton : colle-le dans le champ que
propose la page (`romule token show` le réaffiche). Enfermé dehors dans les
trois cas :

```sh
docker compose exec romule python3 -m romule access open
docker compose restart
```

## J'ai perdu le jeton d'accès

Plus rien n'en engendre, mais si tu en as posé un :

```sh
docker compose exec romule python3 -m romule token show
python3 -m romule token show            # sans Docker
```

`token reset` le remplace — tout navigateur qui avait retenu l'ancien redemande
le nouveau au chargement suivant.

## J'ai oublié mon mot de passe et il n'y a pas de second compte

```sh
docker compose exec romule python3 -m romule user passwd toi@exemple.fr
```

Ou rouvre la porte et règle cela depuis l'interface :

```sh
docker compose exec romule python3 -m romule access open
docker compose restart
```

`open` désactive aussi l'authentification — les comptes ne sont pas touchés, et
`access close` la remet en service.

## L'adresse affichée au premier démarrage ne répond pas

Si elle commence par `172.`, tu lis l'adresse du conteneur sur le réseau de
Docker, que rien ne route. Romule ne l'affiche plus, mais une version
antérieure le faisait. Depuis la machine qui héberge le conteneur,
`http://localhost:8787` fonctionne ; pour toutes les autres, déclare la tienne :

```yaml
environment:
  ROMULE_PUBLIC_HOST: "192.168.1.20"     # ta machine, pas le conteneur
```

Voir [Dans un conteneur](configuration.fr.md#dans-un-conteneur).
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

## « protocol fault (couldn't read status message): Success »

Le message d'adb pendant l'appairage. Le mot « Success » à la fin est un code
d'erreur système, pas un résultat : il ne veut rien dire ici.

Romule démarre désormais le démon adb avant d'appairer, puis retente une fois —
la cause la plus fréquente était que `adb pair` lançait lui-même le démon et
courait contre son propre démarrage. Si le message revient malgré tout :

1. le code d'appairage n'est valable **qu'une fois et quelques minutes**.
   Ferme la fenêtre sur la console, rouvre « Associer un appareil avec un
   code » : tu obtiens un nouveau code **et un nouveau port** ;
2. recopie les deux, ensemble. Le port de la fenêtre d'appairage change à
   chaque ouverture ;
3. vérifie que la console et Romule sont sur le même réseau. Depuis un
   conteneur en mode *bridge*, c'est le cas si le port est publié, mais un
   réseau invité ou un Wi-Fi avec isolation des clients ne laisse rien passer.

## Repartir de zéro pour retester l'installation

L'état du service — configuration, comptes, jaquettes, jeton, « l'assistant a
déjà été vu » — vit dans le volume nommé `romule-donnees`. **Tes jeux n'y sont
pas** : ils sont dans le dossier que tu as monté sur `/library`, et rien ici
n'y touche.

```sh
docker compose down -v          # arrête ET supprime le volume de données
docker compose up               # redémarre sur une installation neuve
```

Le `-v` est tout le sujet : `docker compose down` seul garde le volume, et tu
retrouves l'assistant déjà fait, l'accès déjà choisi, les comptes déjà là.

Pour vérifier ce qui va disparaître avant de le faire :

```sh
docker volume ls | grep romule
```

Si tu as monté un dossier de l'hôte au lieu du volume nommé, `-v` ne le touche
pas — c'est un choix de `docker-compose.yml`, et il faut alors vider ce dossier
à la main.

## L'appairage a réussi, mais la console ne se connecte pas

Presque toujours la même cause : l'adresse saisie pour se connecter est celle de
la **fenêtre d'appairage**. Son port est jetable, il ne sert qu'une fois.

Ferme la fenêtre du code. Derrière elle, l'écran **Débogage sans fil** affiche sa
propre ligne « Adresse IP et port » — un autre port. C'est celui-là qu'attend
l'étape 4 de l'assistant.

Si l'adresse est la bonne et que la connexion échoue quand même, la console a
sans doute quitté le réseau ou changé d'adresse : le port de connexion change à
chaque redémarrage du débogage sans fil, et il faut refaire l'étape 4 (pas
l'appairage, qui reste acquis).

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
