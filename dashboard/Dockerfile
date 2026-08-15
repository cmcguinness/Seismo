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

RUN pip install --no-cache-dir obspy python-fasthtml

# Which commit this image was built from. deploy.sh passes it; a manual `docker build`
# leaves it "unknown". Visible via `docker image inspect` and to the app as
# SEISMO_BUILD_SHA, so a running dashboard can say what it is -- pi5 has no git repo and
# nothing else records the deployed version (that is how signatures.json drifted for two
# weeks unnoticed, 2026-08-12).
ARG GIT_SHA=unknown
ENV SEISMO_BUILD_SHA=$GIT_SHA

WORKDIR /app
COPY seismo_dashboard.py render.py heli_build.py heli_render.py heli_service.py sources.py usgs_events.py /app/
# epochs.py is the analysis copy, rsync'd in by deploy.sh -- see activity.py.
COPY activity.py content.py epochs.py /app/
COPY signatures.json /app/
COPY station.jpg /app/

EXPOSE 5000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "seismo_dashboard.py"]
