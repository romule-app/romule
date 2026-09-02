# Sécurité et exposition

Voir aussi **[Rôles et accès](roles.md)** pour savoir qui a le droit de quoi,
dans chacun des trois modes d'authentification.

## Romule n'a pas de TLS

Il parle du HTTP en clair. Tout ce qui est joignable depuis internet a besoin
d'un proxy inverse terminant le HTTPS devant lui. C'est une limite délibérée,
pas un oubli : une pile TLS écrite à la main serait une plus mauvaise idée que
de déléguer à nginx, Caddy ou Traefik.

## Le piège du proxy inverse

Un proxy sur la même machine fait paraître **toutes** les requêtes comme venant
de `127.0.0.1`. Or Romule accorde tous les droits aux requêtes locales : une
mise en place naïve laisserait donc entrer n'importe qui depuis internet dès
l'instant où l'on place un proxy devant.

Romule ignore donc `X-Forwarded-For` et `X-Real-IP` **tant que tu ne nommes pas
le proxy toi-même** :

```sh
ROMULE_TRUSTED_PROXIES=127.0.0.1,::1
```

Sans cela, un en-tête transmis n'accorde rien — et une requête qui en porte un
n'est pas non plus traitée comme locale. Avec, l'adresse du client est prise
dans l'en-tête, mais seulement si la requête vient réellement d'un proxy listé.

!!! danger "Ne saute pas cette étape"
    Derrière un proxy et sans `ROMULE_TRUSTED_PROXIES`, tous les utilisateurs
    partagent une seule adresse apparente. La limitation de débit et les
    décisions d'accès se dégradent l'une comme l'autre.

## Comment l'accès est décidé

Dans cet ordre :

1. **Authentification active ?** Une session valide est exigée — y compris
   depuis la machine elle-même. Activer un SSO et rester joignable sans mot de
   passe depuis l'hôte viderait la mesure de son sens sur un poste partagé.
2. **Requête venue de cette machine ?** Autorisée.
3. **Un jeton est posé ?** Il doit correspondre, comparé en temps constant.
4. **Sinon** — autorisée seulement si `lan_access` est actif.

## Le jeton de premier accès

Un service joignable mais sans compte, sans jeton et sans accès réseau
refuserait toutes les requêtes — y compris celle qu'il faut pour atteindre les
réglages et corriger le problème. Plutôt que d'ouvrir la porte, Romule engendre
un jeton au premier démarrage et l'affiche avec l'adresse complète :

```
Acces : ce service est joignable par le reseau et n'a pas encore de compte.
        http://192.0.2.20:8787/?token=Kzrmfve...
```

Il est conservé dans ton dossier de jeux, survit aux redémarrages, et n'est
jamais envoyé au navigateur avec le reste de la configuration. Rien n'est
engendré quand Romule n'écoute que sur `127.0.0.1`.

## Comptes et rôles

- Le **premier compte créé est l'administrateur**. Lui seul change les
  réglages, gère les comptes ou lance les actions destructrices.
- Ce premier compte ne peut être créé que **depuis la machine qui héberge la
  ludothèque** — sinon « le premier compte gouverne » voudrait dire « le
  premier appareil du réseau gouverne ».
- Il n'y a jamais zéro administrateur : le dernier ne peut pas être supprimé.
- Les mots de passe passent par scrypt (N=2¹⁷). Le second facteur TOTP est
  disponible par compte.

## Parcourir le système de fichiers de l'hôte

Le sélecteur de ludothèque liste les dossiers de la machine qui fait tourner
Romule. C'est une primitive de divulgation, et elle est traitée comme telle :

- elle est **réservée à l'administrateur**, comme toutes les routes
  destructrices ;
- elle rend **des dossiers seulement** — aucun nom de fichier ne quitte le
  serveur. Le seul nombre supplémentaire est un décompte de jeux reconnus,
  parce que c'est lui qui permet de distinguer ta ludothèque d'un dossier qui
  lui ressemble ;
- choisir un dossier obéit à la même règle que le parcourir : taper un chemin
  n'est donc pas un moyen de contourner `ROMULE_BASES`.

`ROMULE_BASES` n'est pas renseigné par défaut, et c'est délibéré : dans un
conteneur, la frontière est la liste des `volumes:`, appliquée par le noyau
plutôt que par du code applicatif ; sur une installation directe, c'est le
compte Unix qui fait tourner le service. Une liste blanche applicative par
dessus donnerait surtout l'impression d'une frontière. Renseigne
`ROMULE_BASES` quand tu tournes en direct sous un compte large.

## Bornes appliquées

| Borne | Défaut | Pourquoi |
|---|---|---|
| Taille d'un envoi | 64 Gio | Un disque saturé est un déni de service |
| Espace libre gardé | 2 Gio | Refuser l'écriture plutôt que remplir le disque |
| Délai de socket | 300 s | Une connexion lente ne doit pas retenir un fil |
| Connexions | 64 | Concurrence bornée |
| Requêtes | 600/min par client | Limitation sur tout `/api/*` |
| Confinement des chemins | — | Dossiers de plateforme, extensions et title ID sont validés |
| Emplacement de la ludothèque | — | Refusé s'il est en lecture seule, ou s'il s'agit de ton dossier personnel, d'une racine de disque ou d'un dépôt de code |

## Faiblesses connues

**`script-src` vaut `'self'` — aucun script en ligne.** C'était la plus grande
faiblesse connue du projet jusqu'à la 0.2.0, et la retirer a demandé toute une
phase : 153 gestionnaires d'événements en ligne, chacun étant une raison pour
le navigateur d'accepter des scripts écrits dans la page.

L'ordre a compté. Un bouton qui cesse de répondre est invisible côté serveur —
aucune requête n'échoue, rien n'est journalisé — le filet a donc été écrit
*d'abord* : un test qui parcourt chaque écran, trouve chaque élément cliquable,
et échoue si l'un n'a pas de gestionnaire. L'écrire honnêtement a demandé trois
corrections, et chacune mérite d'être dite parce que chacune était une idée
fausse sur le DOM :

- un gestionnaire posé en **propriété** (`el.onclick = fn`) n'apparaît dans
  aucun attribut, et `querySelectorAll('[onclick]')` ne le voit pas ;
- un `<select>` ou une case à cocher répond **nativement** — le geste a un
  effet visible et la valeur est relue à l'enregistrement. Pas inerte, juste
  sans code ;
- `document` n'est pas un `Element` : remonter les `parentElement` ne
  l'atteint jamais — or c'est là que porte la délégation.

Les gestionnaires portent désormais leur action en **donnée** : `data-act`
nomme l'action, `data-arg` son argument. `ACTES` est une liste blanche, pas un
appel dynamique — `app[el.dataset.act]()` aurait été soixante lignes plus court
et aurait laissé n'importe quel attribut atteindre n'importe quelle méthode, y
compris celles qui suppriment.

Le gain de sécurité n'est pas un échappement plus solide, c'est **un analyseur
en moins**. Une valeur placée dans `onclick="app.faire('ICI')"` en traversait
**deux** : l'analyseur HTML décodait les entités, puis le moteur JavaScript
compilait ce qu'il en restait — le `&#39;` d'`esc()` redevenait donc une
apostrophe *avant* que le script ne soit lu, la chaîne se refermait, et la
suite de la valeur devenait du code. Un nom de fichier suffisait à en
fabriquer un, et la clé d'une carte est le chemin du fichier. C'était l'XSS
stockée corrigée en 0.1.0, et `jsq()` en était le bon correctif.

Dans `data-arg="ICI"`, il n'y a qu'un analyseur et rien n'est jamais compilé.
`esc()` suffit — et un test vérifie qu'il est présent sur les 28 sites, car un
guillemet double dans un nom de fichier sortirait sinon de l'attribut.

`jsq()` reste défini, avec ses tests d'aller-retour, comme garde-fou du jour où
quelqu'un réintroduira un gestionnaire en ligne. Deux invariants plus forts
remplacent son ancien rôle : aucun attribut `on*=` n'est engendré nulle part,
dans aucun des deux fichiers, et le test navigateur écoute
`securitypolicyviolation` — une violation de la politique de contenu ne casse
pas la page, elle écrit une ligne en console et continue, ce qui est exactement
le genre d'échec silencieux que ce projet n'arrête pas de trouver. Ce contrôle
est lui-même prouvé : il injecte un script en ligne et vérifie que le
navigateur refuse de l'exécuter.

**`style-src` tolère encore `'unsafe-inline'`.** Les attributs `style=` restent
nombreux dans le balisage engendré. Un style ne s'exécute pas : c'est une
faiblesse d'une autre nature que la précédente — gardée, et dite.

**Pas de TLS**, comme ci-dessus.

**Les [fonctions bêta](beta.md)** portent leurs propres risques, listés là-bas.
La plus sensible du point de vue de la sécurité est le SSO OpenID Connect.

## Vérifier ta propre installation

```sh
python3 -m romule.audit
```

Il rend compte de la configuration réellement en service : exposition,
authentification, en-têtes, permissions de fichiers, dépendances, version de
Python. L'intégration continue échoue sur tout ce qu'il classe *grave*.
Lance-le après chaque changement.

## Signaler une vulnérabilité

En privé, pas dans le suivi de tickets. Voir
[SECURITY.md](https://github.com/romule-app/romule/blob/main/SECURITY.md).
