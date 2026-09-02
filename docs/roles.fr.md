# Rôles et accès

Romule a **deux rôles**, et pas davantage. Un administrateur change les
réglages et gère les comptes. Tous les autres ont la bibliothèque et les gestes
qui vont avec — envoyer vers la console, convertir, mettre à la corbeille.

Il n'y a pas de troisième rôle, ni de tableau de permissions par
fonctionnalité. Un gestionnaire de ludothèque auto-hébergé, utilisé par un
foyer ou une petite équipe, n'en a pas besoin — et toute permission qu'on ne
sait pas expliquer est une permission que personne ne réglera correctement.

## Trois modes, et ce que « rôle » y veut dire

| Mode | Qui entre | Qui administre |
|---|---|---|
| **Sans authentification** (défaut) | quiconque atteint le port | tout le monde |
| **Comptes internes** | quiconque a un compte | les comptes marqués administrateur |
| **OpenID Connect** ([bêta](beta.md)) | qui ton fournisseur autorise, restreint par `oidc_emails` / `oidc_groupes` | les membres de `oidc_admin_groupes` |

!!! info "Sans authentification, tout le monde est administrateur"
    Ce n'est pas un oubli : c'est la façon la plus courante de faire tourner
    Romule, sur un réseau domestique, par une seule personne. Il n'y a aucune
    identité à vérifier, donc rien à distinguer. L'audit intégré le signale à
    chaque démarrage, parce que cela mérite d'être su plutôt que caché.

## Comptes internes

**Le premier compte créé est l'administrateur**, et il ne peut être créé que
depuis la machine qui héberge la ludothèque. Sans cette restriction, « le
premier compte est administrateur » voudrait dire « le premier venu sur le
réseau devient administrateur ».

Un administrateur peut en promouvoir un autre. Romule refuse de retirer le
dernier : une instance que personne ne peut administrer est une instance qu'il
faut réparer à la main, dans un fichier.

## OpenID Connect : deux questions différentes

`oidc_groupes` dit **qui peut entrer**. `oidc_admin_groupes` dit **qui peut
administrer**. Les confondre donnerait l'administration à tous ceux que ton
fournisseur authentifie.

```
oidc_groupes        = romule-users      ← peut ouvrir la bibliothèque
oidc_admin_groupes  = romule-admins     ← peut ouvrir les Réglages
```

**Vide veut dire personne.** Si `oidc_admin_groupes` n'est pas renseigné,
aucune session SSO n'est administratrice. Un réglage vide ne doit jamais
vouloir dire « tout le monde ».

Le rôle est lu dans le jeton d'identité **à l'ouverture de la session**.
Retirer quelqu'un d'un groupe le déclasse à sa **prochaine** connexion, pas au
milieu de celle en cours — l'alternative serait d'appeler ton fournisseur à
chaque requête. C'est le comportement de la plupart des intégrations SSO ; il
est dit ici plutôt que supposé.

!!! tip "Tu ne t'enfermeras pas dehors"
    Activer l'authentification depuis un navigateur déjà autorisé remet à ce
    navigateur un laissez-passer de trente minutes, le temps de finir de te
    configurer — y compris de renseigner `oidc_admin_groupes` — avant que quoi
    que ce soit n'exige un rôle que tu n'as pas encore accordé.

## Ce qu'un non-administrateur ne peut pas faire

Vingt-sept routes lui sont réservées côté serveur. Elles se rangent en six
familles :

- **effacer ou remettre en place des données** — restaurer une sauvegarde
  remet le fichier des comptes, donc rendrait l'administration à qui l'a
  perdue ;
- **déplacer des fichiers en masse** — réorganiser la ludothèque ou la console ;
- **écrire dans les fichiers d'un autre logiciel** — configuration
  d'émulateur, NAND ;
- **changer la liaison à la console** — appairage Wi-Fi, oubli d'un appareil ;
- **désigner où le service lit et écrit sur la machine hôte** — le sélecteur
  de dossiers et l'emplacement de la ludothèque. Parcourir le système de
  fichiers de l'hôte est une primitive de divulgation, et elle est traitée
  comme telle ;
- **renseigner sur qui se connecte et sur la posture de sécurité** — journal
  des accès, audit.

L'interface masque ce que le rôle ne peut pas utiliser : un non-administrateur
ne voit pas l'onglet Réglages. C'est une politesse, **pas** la frontière de
sécurité. Le serveur refuse quoi qu'affiche l'interface, et la suite de tests
vérifie les vingt-sept routes face à un compte ordinaire — pour les comptes
internes comme pour les sessions SSO.

## Les clés d'API sont une troisième chose

Une [clé d'API](api.md) n'est ni un compte ni un rôle. Elle atteint
`/api/v1/` et rien d'autre : elle ne peut ni ouvrir l'interface, ni lire la
configuration, ni toucher aux comptes.

Présenter une clé ne *donne* pas des droits, cela *choisit un régime*. Une
requête venue de `127.0.0.1` obtient normalement tous les droits locaux — mais
dès qu'elle porte `X-Api-Key`, c'est la clé qui décide, et la clé est portée.
Une clé ne peut jamais élargir un accès : au mieux, elle le restreint.
