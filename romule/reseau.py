"""Sorties reseau : un seul point de passage, et un seul controle.

`urllib.request.urlopen` n'ouvre pas que du HTTP. Il accepte `file://`, `ftp://`
et tout ce que les gestionnaires installes savent traiter. Or trois adresses
utilisees par Romule viennent de la CONFIGURATION :

    cover_url      la source des jaquettes
    versions_urls  les miroirs de la base titledb
    oidc_issuer    l'emetteur d'identite

Un `file:///etc/passwd` dans le champ des jaquettes faisait donc lire un
fichier local au serveur, qui le renvoyait ensuite comme une image. Il faut
etre administrateur pour poser ces champs, ce qui limite la portee — mais un
administrateur n'a pas a pouvoir transformer le service en lecteur de fichiers
par un champ de reglage, et une installation ou l'authentification est eteinte
n'a justement pas d'administrateur distinct.

Le controle est ici, dans le seul chemin par lequel toutes les sorties passent,
plutot que repete a neuf endroits ou l'un finirait par etre oublie.
"""

import urllib.error
import urllib.parse
import urllib.request

SCHEMAS = ("http", "https")


class SchemaRefuse(ValueError):
    """Adresse dont le schema n'est pas autorise."""


def verifier(url):
    """Rend l'URL si elle est acceptable, leve `SchemaRefuse` sinon."""
    schema = urllib.parse.urlparse(str(url or "")).scheme.lower()
    if schema not in SCHEMAS:
        raise SchemaRefuse(
            "schema refuse : %r (seuls %s sont acceptes)"
            % (schema or "aucun", " et ".join(SCHEMAS)))
    return url


def ouvrir(cible, timeout=30):
    """`urlopen`, mais seulement en http(s).

    Accepte une chaine ou une `Request`, comme `urlopen`, pour pouvoir se
    substituer aux appels existants sans les reecrire.
    """
    url = cible.full_url if isinstance(cible, urllib.request.Request) else cible
    verifier(url)
    # C'est LE seul `urlopen` du code livre, et le schema vient d'etre verifie
    # deux lignes plus haut. Les marques portent leur raison : les outils ne
    # peuvent pas voir cette verification, et une marque sans motif se recopie
    # ensuite partout.
    # Le motif est ecrit AU-DESSUS, jamais a la suite de la marque : bandit lit
    # ce qui suit celle-ci comme une liste d'identifiants de regle, et une
    # phrase y devient une suite de faux noms de test. (Ce commentaire evite
    # pour la meme raison d'ecrire la marque en toutes lettres.)
    return urllib.request.urlopen(cible, timeout=timeout)  # nosec B310  # noqa: S310
