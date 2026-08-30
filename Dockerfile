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
COPY switch.py ./
COPY switchlib ./switchlib

ENV SWITCH_ROOT=/library \
    SWITCH_WEB_PORT=8787 \
    PYTHONUNBUFFERED=1

# /library      : la ludotheque (jeux, _import, _corbeille, _saves...)
# /root/.switch : prod.keys (lecture seule suffit)
VOLUME ["/library", "/root/.switch"]

EXPOSE 8787

# Sonde de sante : le service repond-il ? (interroge en local, donc sans jeton)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import os,urllib.request;\
urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('SWITCH_WEB_PORT','8787'),timeout=4)" \
  || exit 1

# Le mode service est detecte automatiquement : aucun navigateur n'est ouvert.
CMD ["python3", "switch.py", "serve"]
