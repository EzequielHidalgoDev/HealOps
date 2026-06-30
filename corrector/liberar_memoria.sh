#!/bin/bash
# Producción: se ejecutaría vía SSH en el servidor real

HOST=$1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Liberando caché de memoria en $HOST"

ssh usuario@$HOST "echo 3 > /proc/sys/vm/drop_caches"

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Memoria liberada en $HOST"
    exit 0
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Fallo al liberar memoria en $HOST"
    exit 1
fi
