#!/bin/bash
# Producción: se ejecutaría vía SSH en el servidor real
# En local Docker: Python llama directamente a docker exec

HOST=$1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando limpieza de swap en $HOST"

ssh usuario@$HOST "swapoff -a && swapon -a"

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Limpieza completada en $HOST"
    exit 0
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Limpieza fallida en $HOST"
    exit 1
fi
