# Ta console

Romule parle à une console portable Android par **adb**. Il a été construit
face à une AYN Thor sous l'émulateur Eden, mais l'appareil et l'émulateur sont
des [profils](profils.md), pas des chemins écrits en dur.

## Appairage en Wi-Fi

L'assistant de premier démarrage demande d'abord **comment la console est
reliée** — avec ou sans câble — et ne montre que le chemin correspondant. Les
réglages contiennent le même assistant pas à pas. En résumé :

1. **Sur la console** — Paramètres → Système → Options pour les développeurs →
   **Débogage sans fil**, à activer.
   *Pas d'options développeur ?* Paramètres → À propos du téléphone, touche
   **Numéro de build** sept fois.
2. **Sur la console** — dans l'écran de débogage sans fil, touche **Associer
   l'appareil à l'aide d'un code**. Laisse la fenêtre ouverte : le code expire
   quand elle se ferme. Elle affiche un code à six chiffres et une adresse du
   type `192.168.1.42:37105`.
3. **Dans Romule** — saisis cette adresse et ce code, puis valide
   l'appairage. Romule essaie ensuite de se connecter tout seul : un lien laissé
   par une session précédente, ce que les consoles annoncent en mDNS, puis le
   port 5555. Si l'une de ces pistes aboutit, il n'y a rien de plus à faire.
4. **Sur la console** *(seulement si aucune piste n'a abouti)* — ferme la
   fenêtre du code. L'écran de débogage sans fil
   affiche derrière elle **sa propre ligne « Adresse IP et port »**, et ce
   n'est pas la même : le port d'appairage ne sert qu'une fois. Recopie
   celle-là dans Romule, puis **Connecter la console**.

Une fois connectée, la console est reconnue toute seule ensuite.

Une fois la connexion faite, le panneau ne demande plus rien : il montre ce que
la console a répondu — son nom, son adresse, sa version d'Android, son niveau de
batterie, depuis combien de temps le lien tient. Ces informations ne peuvent pas
s'afficher si la console n'a pas répondu, ce qui les rend plus utiles qu'un
simple « connectée ».

!!! note "Sous Docker, l'étape 4 est la règle"
    La console annonce son port de connexion en **mDNS**, et le multicast ne
    traverse pas le pont Docker. Depuis un conteneur, Romule ne peut donc pas le
    deviner : il faut le lire sur l'écran de la console. Sur une installation
    directe, la découverte marche et l'étape 4 ne s'affiche presque jamais.

!!! warning "Deux adresses, deux ports"
    C'est le point où l'on se trompe. La fenêtre du code donne un port
    d'appairage, jetable ; l'écran de débogage sans fil en donne un autre, celui
    de la connexion. Saisir le premier à l'étape 4 échoue sans rien expliquer.

!!! note "Le Wi-Fi est plus lent"
    Deux à cinq fois plus lent que l'USB sur les gros transferts. Sans
    importance pour quelques jeux, très sensible pour une ludothèque entière.

## USB

Branche la console, débogage activé, et appuie sur **Détecter**. Sous Docker,
l'USB demande `devices: - /dev/bus/usb:/dev/bus/usb` et Linux — voir
[Installation](installation.md#reseau).

## Le dossier des jeux

Romule le détecte, et l'affiche une fois connecté :

```
/storage/emulated/0/Switch
```

Change-le dans **Réglages → Ta console** si ton émulateur range les jeux
ailleurs. Le réglage **Dossier des ROMs** est le parent de toutes les autres
plateformes, chacune dans son sous-dossier (`GBA`, `SNES`, `PS2`…). Laissé
vide, il est déduit du dossier Switch.

## Une plateforme que Romule ne connaît pas

Vingt-trois plateformes sont reconnues d'origine, et la liste n'est pas une
limite. **Réglages → Ta console → Ajouter une plateforme…** demande trois
choses :

| Champ | Exemple | À quoi il sert |
|---|---|---|
| Nom affiché | `Neo Geo` | Ce que tu verras dans le sélecteur de plateformes |
| Dossier sur la console | `NeoGeo` | Un sous-dossier du dossier des ROMs ci-dessus |
| Extensions | `zip, neo` | Ce qui compte comme un jeu pour cette plateforme |

Cela suffit pour que la plateforme soit analysée, filtrée, comptée et envoyée
comme les autres. C'est aussi la réponse quand une console *est* connue mais
que tu la ranges dans un dossier que Romule ne devinerait pas : déclare-la sous
le nom que tu emploies réellement.

Les plateformes ajoutées sont rangées sous `systemes_perso` dans le fichier de
réglages, et suivent tes sauvegardes.

!!! note "Ce que cela ne fait pas"
    Déclarer une plateforme n'apprend pas à Romule à lire l'*intérieur* de ses
    fichiers. La Switch est la seule qu'il ouvre : les title ID, les liens
    base/mise à jour/DLC et les mises à jour manquantes viennent de l'analyse
    du conteneur. Toute autre plateforme — livrée ou ajoutée — est identifiée
    par son dossier et son extension.

## Rangement sur la console

Les fichiers Switch sont triés en `GAMES`, `UPDATE` et `DLC`. Le type vient du
*contenu* du fichier quand Romule sait le lire, pas de son nom — un nom ment
assez souvent : un title ID tronqué, absent, ou un fichier qui annonce un jeu
de base alors qu'il s'agit d'une mise à jour.

## Ce qui s'y trouve déjà

**Lister les jeux de la console** rapporte ce qu'elle contient et combien
manquent à ta ludothèque, pour ne pas réimporter ce qui est déjà là.

## Adb n'est pas installé

Romule le dit et donne la commande pour ta plateforme. Rien d'autre ne cesse de
fonctionner : la bibliothèque, les jaquettes et l'inventaire n'ont pas besoin
d'une console.
