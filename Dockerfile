# Ludotheque Switch — service auto-heberge (NAS, mini-PC, serveur).
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

# Le mode service est detecte automatiquement : aucun navigateur n'est ouvert.
CMD ["python3", "-m", "romule", "serve"]
