#!/bin/bash
# Producción: se ejecutaría vía SSH en el servidor real

HOST=$1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Analizando CPU en $HOST"

# Identifica el proceso pero NO lo mata — escala a ticket si es crítico
PROCESO=$(ssh usuario@$HOST "ps aux --sort=-%cpu | awk 'NR==2{print \$11\" PID:\"\$1\" CPU:\"\$3\"%'}")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Proceso con más CPU: $PROCESO"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Escalando a ticket — intervención manual requerida"
exit 1  # fuerza apertura de ticket en GLPI
