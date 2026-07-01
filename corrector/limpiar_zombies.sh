#!/bin/bash
# Producción: los procesos zombie no se pueden matar directamente.
# Se identifican y se intenta reiniciar el proceso padre.
# Si no se resuelve, escala a ticket (exit 1).

HOST=$1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Analizando procesos zombie en $HOST"

ssh usuario@$HOST bash << 'EOF'
  ZOMBIES=$(ps aux | awk '$8 == "Z" {print $2, $11}')
  COUNT=$(echo "$ZOMBIES" | grep -c . || true)

  if [ "$COUNT" -eq 0 ]; then
    echo "Sin procesos zombie activos."
    exit 0
  fi

  echo "Procesos zombie detectados ($COUNT):"
  echo "$ZOMBIES"

  # Intentar reiniciar el padre de cada zombie
  while IFS= read -r line; do
    PID=$(echo $line | awk '{print $1}')
    PPID=$(ps -o ppid= -p $PID 2>/dev/null | tr -d ' ')
    if [ -n "$PPID" ] && [ "$PPID" -ne 1 ]; then
      echo "Reiniciando proceso padre PID $PPID..."
      kill -HUP $PPID 2>/dev/null || true
    fi
  done <<< "$ZOMBIES"

  # Verificar si persisten tras el intento
  sleep 3
  RESTANTES=$(ps aux | awk '$8 == "Z"' | grep -c . || true)
  if [ "$RESTANTES" -gt 0 ]; then
    echo "Siguen activos $RESTANTES zombies — requiere intervención manual."
    exit 1
  fi
  echo "Zombies resueltos."
EOF
