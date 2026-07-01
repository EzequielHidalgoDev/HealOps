#!/bin/bash
# Producción: verifica conectividad SSH y reinicia el servicio si no responde.
# Se ejecuta desde un servidor de gestión externo con acceso por otro medio (p.ej. consola).

HOST=$1
PUERTO=${2:-22}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Verificando SSH en $HOST:$PUERTO"

# Comprobar si el puerto responde
if nc -z -w5 $HOST $PUERTO 2>/dev/null; then
  echo "SSH responde correctamente en $HOST:$PUERTO"
  exit 0
fi

echo "SSH no responde — intentando reinicio via consola de gestión..."

# En producción real esto usaría IPMI/iLO/iDRAC o una VPN de gestión.
# Aquí se simula con SSH por un puerto alternativo o usuario de emergencia.
ssh -p 2222 admin@$HOST "sudo systemctl restart sshd && echo 'SSH reiniciado'" 2>/dev/null

sleep 5
if nc -z -w5 $HOST $PUERTO 2>/dev/null; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSH restaurado en $HOST"
  exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] SSH sigue sin responder — escalando a ticket"
exit 1
