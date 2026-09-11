# Sauvegardes

Un jeu se retélécharge. Deux cents heures de progression, non — pas plus que le
fichier des comptes ou les jaquettes qu'on a passé une soirée à corriger à la
main.

Romule faisait déjà un tiers de ce travail, à trois endroits, et aucun ne disait
où la copie se posait : la configuration allait dans `_sauvegardes/`, les
sauvegardes de jeu de la console dans `_saves/`, et la ludothèque tenait dans un
dossier. Les trois écrivaient **sur le même disque que ce qu'ils protégeaient**,
c'est-à-dire contre la seule panne pour laquelle une sauvegarde existe.

**Réglages → Sauvegardes**, c'est ce travail, fait en un seul endroit.

## Les quatre questions

Tout se choisit dans une fenêtre, dans l'ordre où l'on se pose les questions.

### Quoi

| Source | Où elle est lue | Remarque |
|---|---|---|
| Sauvegardes de jeu | la console, par adb | Laissées de côté, avec une ligne au journal, si aucune console ne répond |
| Jeux | la ludothèque | |
| Mises à jour | la ludothèque | |
| DLC | la ludothèque | |
| Jaquettes et fiches | le dossier de données | Petit, et long à reconstruire |
| Configuration et comptes | le dossier de données | L'historique que `backup.py` tenait déjà y est inclus |

Chaque ligne annonce ce qu'elle pèse avant qu'on la coche. Les sauvegardes de
jeu font exception et le disent : leur taille n'est connue qu'en lisant la
console.

### Depuis quelle console

Posée seulement si les sauvegardes de jeu font partie du lot. Elle désigne la
console pilotée — le même réglage que **Réglages → Ta console → Mes consoles** —
et dit si elle est connectée, puisque c'est ce qui décide si ses sauvegardes
entrent dans le lot.

### Où

Romule propose ce qu'il trouve plutôt qu'un champ à remplir :

- **un disque branché** — tout ce qui est monté sous `/Volumes`, `/media`,
  `/run/media` ou `/mnt`. C'est la destination qui survit à la panne ;
- **un dossier synchronisé** — Dropbox, Google Drive, OneDrive, Nextcloud,
  pCloud, Syncthing. Romule écrit des fichiers dans le dossier que leur client
  surveille déjà ; c'est ce client qui les emporte. **Aucun compte, aucun jeton,
  aucun appel réseau depuis Romule** — ce qui est aussi la raison pour laquelle
  ça continue de marcher quand un fournisseur change son API ;
- **le dossier de données du service**, proposé en dernier et nommé *Même
  machine*. Une copie vaut mieux que pas de copie, et c'est quand même celle
  qui part avec le disque.

Tout le reste passe par **Choisir un autre dossier…**, qui parcourt l'hôte et
sait y créer des dossiers.

!!! warning "Absolue, et bornée par `ROMULE_BASES`"
    Un chemin relatif est refusé : il se lirait depuis le dossier où tourne le
    service — différent dans un conteneur, une unité systemd et un terminal —
    et `../sauvegardes` désignerait donc un endroit différent sur chaque
    machine. Une destination hors des dossiers déclarés est refusée elle aussi,
    et n'est pas créée. Le raisonnement est celui du sélecteur de dossiers :
    dans un conteneur, les montages sont la liste blanche, et c'est le noyau
    qui l'applique. Voir [Rôles et accès](roles.fr.md).

### À quel rythme

Les cinq mêmes réglages que toute tâche planifiée — jamais, au démarrage, toutes
les heures, toutes les six heures, chaque nuit à une heure choisie. Le réglage
est partagé avec **Réglages → Entretien → Planification** : un réglage, deux
endroits pour l'atteindre.

## Ce que fait une exécution

1. elle résout les sources choisies en une liste de fichiers, avec leur poids
   total ;
2. elle **refuse si la destination n'a pas la place** — avant de copier quoi que
   ce soit. Le découvrir à 94 %, c'est le découvrir trop tard, et cela laisse un
   demi-lot qui ressemble à un lot entier. Si de vieux lots occupent la place,
   la rotation passe en avance, et le dit ;
3. elle copie, avec un avancement et un ETA calculé sur le débit mesuré. La
   tâche se met en pause et s'annule comme toutes les autres ;
4. elle écrit `manifeste.json` dans le lot ;
5. elle fait la rotation : le plus ancien d'abord, jusqu'au nombre demandé.

Chaque étape passe par le journal. Une copie sans surveillance qui ne dit rien
est une copie que personne ne vérifie.

## À quoi ressemble un lot

```
/Volumes/Sauvegardes/
  romule-2026-09-11_031500/
    manifeste.json
    sauvegardes/storage_emulated_0_Android_data_…/
    jeux/Zelda/Zelda.nsp
    config/_romule-config.json
```

`manifeste.json` dit ce que le lot contient, quand il a été pris, depuis quelle
ludothèque, et s'il est allé au bout :

```json
{
  "outil": "romule",
  "date": "2026-09-11 03:15:00",
  "sources": ["sauvegardes", "jeux"],
  "fichiers": 1284,
  "octets": 41203847168,
  "complet": true,
  "ludotheque": "/library"
}
```

Des dossiers et des fichiers ordinaires : **un lot se restaure en le recopiant**,
avec ou sans Romule. C'est l'objet même d'une sauvegarde, et c'est pourquoi rien
ici n'est un format d'archive.

## La rotation, et ce qu'elle ne supprimera pas

La rotation supprime. Elle ne regarde donc que les dossiers qui portent **à la
fois** notre préfixe et notre manifeste — un dossier de photos de vacances posé
à côté des lots n'est pas un candidat, et un dossier qui se trouve simplement
porter un nom voisin non plus.

Un lot **interrompu** part avant un lot complet : garder une demi-copie à la
place d'une copie entière est la seule façon dont la rotation pourrait aggraver
les choses.

Deux sauvegardes dans la même seconde reçoivent un suffixe plutôt que l'une
d'écraser l'autre. Un lot existant est une sauvegarde, et Romule n'écrit pas
par-dessus une sauvegarde.

## Ce que ce n'est pas

Ce n'est **pas** une synchronisation, ni une archive à versions. Chaque lot est
une copie entière de ce qu'on a coché. Sauvegarder toute une ludothèque chaque
nuit remplira n'importe quel disque qu'on lui désigne — c'est à cela que sert
`backup_keep`, et c'est pourquoi le défaut ne porte que les sauvegardes de jeu.
