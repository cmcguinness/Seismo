#!/bin/sh
# Seismo station login banner. Installed as /etc/update-motd.d/50-seismo (0755).
# Kept fast: only `systemctl is-active` + an ls. Shows live recorder status.
DATA=/home/charles/seismo/data

if systemctl is-active --quiet seismo-recorder 2>/dev/null; then
    STATUS="[ RECORDING ]"
else
    STATUS="[ STOPPED ]  <-- not recording!"
fi

printf '\n'
printf '=== Seismo -- DIY geophone seismometer (AM.OAKMT.00.SHZ) ===\n'
printf '  recorder service: %s\n' "$STATUS"
LATEST=$(ls -t "$DATA"/*.mseed 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    printf '  latest day-file : %s (%s)\n' "$(basename "$LATEST")" "$(du -h "$LATEST" | cut -f1)"
fi
cat <<'EOF'

  status : systemctl status seismo-recorder
  logs   : journalctl -u seismo-recorder -f
  data   : ls -lh ~/seismo/data/

  NOTE: the recorder OWNS the ADC while running. Before running any manual
  ADC tool (live_view.py / adc_diag.py / noise_compare.py / recorder.py):
      sudo systemctl stop  seismo-recorder     # frees the ADC
      sudo systemctl start seismo-recorder     # resume recording
EOF
printf '\n'
