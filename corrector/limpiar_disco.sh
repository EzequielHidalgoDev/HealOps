#!/bin/bash
# Producción: libera espacio en disco eliminando logs antiguos y temporales

HOST=$1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando limpieza de disco en $HOST"

ssh usuario@$HOST bash << 'EOF'
  echo "--- Espacio antes ---"
  df -h /

  # Eliminar logs del sistema con más de 7 días
  find /var/log -type f -name "*.log" -mtime +7 -delete
  find /var/log -type f -name "*.gz" -mtime +3 -delete

  # Vaciar directorio temporal
  find /tmp -type f -mtime +1 -delete

  # Limpiar caché de paquetes (compatible Debian/RHEL)
  if command -v apt-get &>/dev/null; then
    apt-get clean -y
  elif command -v yum &>/dev/null; then
    yum clean all
  fi

  echo "--- Espacio después ---"
  df -h /
EOF

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Limpieza de disco completada en $HOST"
