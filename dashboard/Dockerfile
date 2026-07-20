# Seismo public dashboard. obspy + python-fasthtml from PyPI wheels (aarch64
# wheels exist for numpy/scipy/matplotlib/obspy, so no source builds / no OOM).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=5000 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir obspy python-fasthtml

WORKDIR /app
COPY app.py render.py /app/

EXPOSE 5000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "app.py"]
