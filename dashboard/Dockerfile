# Seismo public dashboard. obspy + python-fasthtml from PyPI wheels (aarch64
# wheels exist for numpy/scipy/matplotlib/obspy, so no source builds / no OOM).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=5000 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp

# build-essential: obspy has no aarch64 py3.12 wheel, so its small C extensions
# compile from source (numpy/scipy/matplotlib still install as wheels).
RUN apt-get update && apt-get install -y --no-install-recommends tini build-essential \
    && rm -rf /var/lib/apt/lists/*

# requests: dc_watch publishes to ntfy. It arrives as an obspy dep anyway, but
# something that imports it directly should ask for it directly.
RUN pip install --no-cache-dir obspy python-fasthtml requests

# Which commit this image was built from. deploy.sh passes it; a manual `docker build`
# leaves it "unknown". Visible via `docker image inspect` and to the app as
# SEISMO_BUILD_SHA, so a running dashboard can say what it is -- pi5 has no git repo and
# nothing else records the deployed version (that is how signatures.json drifted for two
# weeks unnoticed, 2026-08-12).
ARG GIT_SHA=unknown
ENV SEISMO_BUILD_SHA=$GIT_SHA

WORKDIR /app
COPY seismo_dashboard.py render.py heli_build.py heli_render.py heli_service.py sources.py usgs_events.py /app/
COPY dc_watch.py /app/
# epochs.py is the analysis copy, rsync'd in by deploy.sh -- see activity.py.
COPY activity.py content.py epochs.py /app/
# The Catches page: its prose module and the static share images + detection map.
# NB this COPY list is explicit, so a new page module MUST be added here or the
# image builds cleanly and then the container dies on import. That is what
# happened to listen.py on 2026-09-02: build green, `ModuleNotFoundError: listen`
# at startup, dokku kept the old container, and the only symptom was a 404.
COPY catches.py listen.py sound.py /app/
COPY catches/ /app/catches/
COPY signatures.json /app/
COPY station.jpg /app/

EXPOSE 5000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "seismo_dashboard.py"]
