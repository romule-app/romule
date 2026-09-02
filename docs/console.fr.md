# Ta console

Romule parle à une console portable Android par **adb**. Il a été construit
face à une AYN Thor sous l'émulateur Eden, mais l'appareil et l'émulateur sont
des [profils](profils.md), pas des chemins écrits en dur.

## Appairage en Wi-Fi

Les réglages contiennent un assistant pas à pas. En résumé :

1. **Sur la console** — Paramètres → Système → Options pour les développeurs →
   **Débogage sans fil**, à activer.
   *Pas d'options développeur ?* Paramètres → À propos du téléphone, touche
   **Numéro de build** sept fois.
2. **Sur la console** — dans l'écran de débogage sans fil, touche **Associer
   l'appareil à l'aide d'un code**. Laisse la fenêtre ouverte : le code expire
   quand elle se ferme. Elle affiche un code à six chiffres et une adresse du
   type `192.168.1.42:37105`.
3. **Dans Romule** — saisis les deux. Une fois appairée, la console est
   reconnue toute seule ensuite.

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
