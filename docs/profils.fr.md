# Profils d'émulateur

L'émulateur décide où Romule dépose les jeux et où il lit les sauvegardes. Il
est décrit par un fichier JSON dans `romule/profils/`, pas par du code.

| Profil | Vérifié sur du matériel réel | Remarques |
|---|---|---|
| **Eden** | **oui** | Le profil de référence. Romule a été construit face à lui. |
| Yuzu | non | Eden en descend : même arborescence, même format de configuration. |
| Sudachi | non | Dérivé de Yuzu. |
| Citron | non | Dérivé de Yuzu. |
| Ryujinx | non | Configuration JSON, et une autre arborescence. |
| Autre émulateur | non | Dossier des jeux seulement, rien de plus. |

Les profils non vérifiés sont étiquetés comme tels dans l'interface. Cette
étiquette est le défaut honnête, pas une clause de style : seul Eden a été
éprouvé face à un vrai appareil.

Choisis le tien dans **Réglages → Ta console**.

## Ce que contient un profil

```json
{
  "cle": "eden",
  "nom": "Eden",
  "paquets": ["dev.eden.eden_emulator", "dev.eden_emu.eden"],
  "donnees": "/storage/emulated/0/Android/data/{paquet}/files",
  "config": { "format": "ini-qt", "fichier": "config/qt-config.ini" },
  "sauvegardes": "nand/user/save",
  "verifie": true
}
```

`paquets` liste les noms de paquet Android possibles, parce qu'ils changent
d'une version d'émulateur à l'autre. Romule demande à la console lequel est
réellement installé plutôt que de deviner, et retient la réponse.

`config` vaut `null` pour les profils dont Romule ne sait pas piloter les
réglages. Quand il est renseigné, le panneau de réglages de l'émulateur
apparaît — et il est étiqueté **bêta**, parce que Romule écrit dans les
fichiers d'un autre logiciel et que ce format peut changer sans préavis.

## Ajouter un profil

Copie `romule/profils/eden.json`, adapte-le, et pose `"verifie": false` à moins
de l'avoir éprouvé face à un vrai appareil. Voir
[Contribuer](contribuer.md).
