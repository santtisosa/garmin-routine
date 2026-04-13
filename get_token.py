"""
Helper para obtener el token de Garmin desde el browser.

El IP de este equipo quedó rate-limited por Garmin. Este script te guía
para extraer el token directamente del browser (donde ya estás logueado)
y guardarlo en ~/.garmin_tokens/garmin_tokens.json para que routine.py
lo use sin necesitar login.

Uso:
    python get_token.py
"""

import json
from pathlib import Path

TOKEN_FILE = Path("~/.garmin_tokens/garmin_tokens.json").expanduser()

INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════╗
║         OBTENER TOKEN DE GARMIN CONNECT DESDE EL BROWSER        ║
╚══════════════════════════════════════════════════════════════════╝

Pasos:

  1. Abrí https://connect.garmin.com en tu browser y asegurate de estar logueado.

  2. Abrí DevTools:
       Chrome/Edge: F12  →  pestaña "Application"
       Firefox:     F12  →  pestaña "Storage"

  3. En el panel izquierdo buscá:
       Local Storage → https://connect.garmin.com

  4. Buscá la clave:  com.garmin.connect.user.di.token

  5. Copiá el valor completo (es un string JSON largo con di_token, di_refresh_token, etc.)

  ─── Alternativa: desde la consola del browser ─────────────────────

     En DevTools → pestaña Console, pegá esto y presioná Enter:

     copy(localStorage.getItem('com.garmin.connect.user.di.token'))

     Eso copia el valor al portapapeles directamente.

  ───────────────────────────────────────────────────────────────────

  6. Pegá el contenido abajo cuando se te pida.

"""

print(INSTRUCTIONS)

raw = input("Pegá el contenido del token aquí y presioná Enter:\n> ").strip()

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("\n✗ El contenido no es JSON válido. Intentá de nuevo.")
    exit(1)

# El localStorage puede devolver el objeto completo o solo los campos del token
# Nos aseguramos de que tenga los campos mínimos
di_token = data.get("di_token") or data.get("accessToken") or data.get("access_token")
di_refresh = data.get("di_refresh_token") or data.get("refreshToken") or data.get("refresh_token")
di_client_id = data.get("di_client_id") or data.get("clientId") or data.get("client_id")

if not di_token:
    print("\n✗ No se encontró 'di_token' en el JSON. Revisá que copiaste el valor correcto.")
    exit(1)

token_data = {
    "di_token": di_token,
    "di_refresh_token": di_refresh,
    "di_client_id": di_client_id,
}

TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
TOKEN_FILE.write_text(json.dumps(token_data, indent=2))

print(f"\n✓ Token guardado en {TOKEN_FILE}")
print("  Ahora podés ejecutar: python routine.py")
