import time
import subprocess
import sys
import os
from datetime import datetime

INTERVALO = 5 * 60  # 5 minutos

script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor", "analizador_alertas.py")

print(f"HealOps Scheduler — ciclo cada {INTERVALO // 60} min")
print("Ctrl+C para detener\n")

while True:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ejecutando análisis...")
    subprocess.run([sys.executable, script])
    print(f"Próximo ciclo en {INTERVALO // 60} minutos\n")
    time.sleep(INTERVALO)
