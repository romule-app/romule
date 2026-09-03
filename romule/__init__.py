"""romule — moteur d'une ludotheque de jeux auto-hebergee.

Source unique de verite : toute la logique metier vit ici, partagee par
l'interface web (server.py) et la ligne de commande (cli.py).

Le coeur connait la Switch en detail (title IDs, NSP/XCI, mises a jour et
DLC) ; les autres plateformes passent par un inventaire par fichier. L'appareil
cible et l'emulateur sont des profils, pas du code (voir profils.py).
"""

__version__ = "0.3.0"

# Romule est distribue sous licence AGPL-3.0-or-later. La licence demande
# qu'un utilisateur qui atteint le service PAR LE RESEAU puisse en obtenir le
# code : c'est le sens du lien affiche en pied d'interface, et de ce que
# renvoie /api/health.
SOURCE_URL = "https://github.com/romule-app/romule"
LICENCE = "AGPL-3.0-or-later"
