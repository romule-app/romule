# Fonctions bêta

Elles fonctionnent, et elles servent. Elles sont étiquetées bêta parce que
chacune porte un risque précis qu'il vaut mieux connaître avant de s'y fier.
L'étiquette apparaît dans l'interface, à côté du réglage.

## SSO OpenID Connect

**Pourquoi bêta.** Romule vérifie les jetons d'identité RS256 avec une
implémentation écrite pour ce projet, sans aucune bibliothèque tierce. Un
vérificateur de JWT est exactement le genre de code où une erreur subtile est
une faille de sécurité plutôt qu'un plantage.

Vingt tests forgent des jetons contre lui, un par attaque connue : `alg: none`,
confusion RS256/HS256 (la clé publique utilisée comme secret HMAC), une clé de
signature étrangère, un `kid` inconnu, une signature altérée, une charge utile
échangée en gardant la signature d'origine, un émetteur faux, une audience
fausse — seule ou dans une liste —, un jeton expiré, un jeton daté du futur, un
nonce qui ne correspond pas, et des entrées malformées de toutes les formes.
Tous sont refusés, et un test témoin vérifie qu'un jeton *valide* passe
toujours : une suite qui rejette tout ne prouve rien.

**Elle reste étiquetée bêta**, parce qu'un test prouve les cas auxquels on a
pensé. Ce code est jeune, il n'a reçu aucun regard extérieur, et une
vérification cryptographique écrite à la main mérite de la prudence plutôt que
de la confiance.

**La voie éprouvée**, ce sont les comptes internes : adresse, mot de passe
haché en scrypt, second facteur TOTP facultatif.

## Pilotage de la configuration d'émulateur

**Pourquoi bêta.** Romule lit et écrit les fichiers de configuration d'un
*autre logiciel*. Ce format appartient à l'émulateur, et il peut changer sans
préavis. Une sauvegarde est prise avant d'écrire, mais la fonction est à une
publication amont de devoir être corrigée.

Seuls les profils qui déclarent une configuration pilotable font apparaître ce
panneau.

## Réglages communautaires EmuReady

**Pourquoi bêta.** Les notes de compatibilité et les réglages recommandés
viennent d'[emuready.com](https://www.emuready.com), une base communautaire
tierce. Romule montre ce qu'elle rapporte ; il ne peut pas s'en porter garant.
Appliquer les réglages recommandés remplace ta configuration actuelle pour ces
jeux.

## Reprise de transfert

**Pourquoi bêta.** Un transfert interrompu peut repartir de son état enregistré
plutôt que d'être relancé. La reprise repart du dernier fichier *confirmé*. Le
cas est réellement difficile à éprouver de bout en bout — il faut une
interruption au bon moment, sur du matériel réel.

Dans le doute, abandonner et renvoyer est plus sûr.

## Résumés Wikipédia

**Pourquoi bêta.** Pour les plateformes dont IGDB ne connaît pas un titre,
Romule se rabat sur une recherche Wikipédia par nom. Le rapprochement par nom
est approximatif : un mauvais résumé sur un titre obscur est un résultat
normal, pas un bogue.

## Le rapport d'audit, les pages de connexion et la ligne de commande sont en français

**Pas bêta — une limite assumée.** L'interface de Romule se traduit
entièrement : chaque phrase vit dans un catalogue, un contrôle d'intégration
continue échoue si l'une lui échappe, et un test navigateur parcourt dix-huit
écrans à la recherche de ce qui reste.

Trois choses sortent de ce mécanisme, parce qu'elles ne sont pas construites
dans le navigateur. Le **rapport d'audit** est composé par le serveur et rendu
en phrases finies ; les **pages de connexion et de refus** sont servies avant
tout JavaScript, ce qui est tout leur intérêt ; la **ligne de commande**
(`romule apikey`, `romule serve`) ne charge jamais l'interface. Les traduire
demande de traduire `romule/audit.py`, `romule/cli.py` et les gabarits de page
de `romule/server.py` — une i18n côté serveur, que Romule n'a pas.

Elles sont en français, langue source du projet. C'est écarté sciemment plutôt
que laissé en test rouge : le test navigateur exclut le panneau d'audit avec
son motif écrit à côté de l'exclusion.

---

## Ce qui n'est *pas* bêta

L'inventaire de la ludothèque, les jaquettes, les transferts vers la console,
les mises à jour et les liens de DLC, les comptes internes, le TOTP, l'audit et
le système de sauvegarde. Ce sont les parties que les suites de tests couvrent
de bout en bout.
