"""
Helper para autenticarse en Garmin Connect desde el browser.

El IP de este equipo está rate-limited por Garmin. Este script usa las
cookies de sesión del browser (donde ya estás logueado) para acceder
a la API sin necesitar hacer login automático.

Uso:
    python get_token.py
"""

import json
from pathlib import Path

SESSION_FILE = Path("~/.garmin_session.json").expanduser()

INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════╗
║       OBTENER SESIÓN DE GARMIN CONNECT DESDE EL BROWSER         ║
╚══════════════════════════════════════════════════════════════════╝

Necesitamos dos valores de la request que ya tenés abierta en DevTools.

─── EN DEVTOOLS → NETWORK ─────────────────────────────────────────

  1. Buscá cualquier request a connect.garmin.com
  2. Click en ella → pestaña "Headers" → "Request Headers"

  Valor 1 — Buscá el header:  JWT_WEB  (está dentro de la línea "cookie")
            Copiá solo el valor del JWT, que empieza con "eyJ..."
            Termina antes del ";" siguiente.

  Valor 2 — Buscá el header:  connect-csrf-token
            Es un UUID tipo: e9ba7558-2dea-449c-a47a-3843f5d843ef

─── ALTERNATIVA: desde la consola del browser ─────────────────────

  Pegá esto en Console para copiar ambos valores de una:

  (()=>{
    const jwt = document.cookie.match(/JWT_WEB=([^;]+)/)?.[1];
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content
      || window.__CSRF_TOKEN__;
    copy(JSON.stringify({jwt_web: jwt}));
    console.log("JWT_WEB copiado. CSRF token (buscalo en Network):", csrf);
  })()

───────────────────────────────────────────────────────────────────
"""

print(INSTRUCTIONS)

jwt_web = input("Pegá el valor de JWT_WEB (empieza con 'eyJ...'):\n> ").strip()
if not jwt_web.startswith("eyJ"):
    print("⚠ El JWT_WEB debería empezar con 'eyJ'. Revisá que copiaste solo el valor, sin 'JWT_WEB='.")

csrf_token = input("\nPegá el valor de connect-csrf-token (UUID):\n> ").strip()

data = {
    "jwt_web": jwt_web,
    "csrf_token": csrf_token,
}

SESSION_FILE.write_text(json.dumps(data, indent=2))
print(f"\n✓ Sesión guardada en {SESSION_FILE}")
print("  Ahora podés ejecutar: python routine.py")
