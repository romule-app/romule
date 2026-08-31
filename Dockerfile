# Romule — ludotheque de jeux auto-hebergee (NAS, mini-PC, serveur).
#
#   docker compose up -d
#
# La console est pilotee par adb *sans fil* : le serveur n'a pas besoin d'un
# port USB, seulement d'etre sur le meme reseau que la console.

FROM python:3.12-slim

# adb  : pilotage de la console (appairage et transfert sans fil)
# unar : extraction des .rar deposes dans _import
# p7zip: extraction des .7z
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      android-tools-adb \
      unar \
      p7zip-full \
 && rm -rf /var/lib/apt/lists/*

# nsz : conversion .nsz/.xcz -> .nsp/.xci
RUN pip install --no-cache-dir nsz

WORKDIR /app
COPY romule ./romule
COPY LICENSE README.md ./

ENV ROMULE_ROOT=/library \
    ROMULE_WEB_PORT=8787 \
    ROMULE_KEYS=/keys/prod.keys \
    PYTHONUNBUFFERED=1

# Un service expose au reseau n'a aucune raison d'etre root. L'identifiant 1000
# est celui du premier compte cree sur la plupart des distributions : les
# fichiers deposes dans la ludotheque appartiendront donc a l'utilisateur, et
# non a root sur son propre NAS.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin romule \
 && mkdir -p /library /keys \
 && chown -R romule:romule /library /keys /app

# /library : la ludotheque (jeux, _import, _corbeille, _saves...)
# /keys    : prod.keys (lecture seule suffit)
VOLUME ["/library", "/keys"]

USER romule

EXPOSE 8787

# Sonde de sante : le service repond-il ? (interroge en local, donc sans jeton)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import os,urllib.request;\
urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('ROMULE_WEB_PORT','8787'),timeout=4)" \
  || exit 1

# En derniere position, et pas en tete : l'etiquette porte le numero de
# version, et une couche qui change a chaque publication invaliderait tout
# ce qui la suit — soit apt et pip, les deux couches les plus lentes.
# Renseigne par la chaine de construction (`--build-arg VERSION=$(git describe)`).
# La valeur par defaut vaut celle du paquet : une image construite a la main
# n'affiche pas « unknown ».
ARG VERSION=0.1.0

LABEL org.opencontainers.image.title="Romule" \
      org.opencontainers.image.description="Self-hosted library manager for the games you own, with transfer to an Android handheld over adb" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/romule-app/romule" \
      org.opencontainers.image.documentation="https://romule-app.github.io/romule/" \
      org.opencontainers.image.url="https://github.com/romule-app/romule"

# Le mode service est detecte automatiquement : aucun navigateur n'est ouvert.
CMD ["python3", "-m", "romule", "serve"]
