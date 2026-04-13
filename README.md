<div align="center">

```
 ██████╗  █████╗ ██████╗ ███╗   ███╗██╗███╗   ██╗
██╔════╝ ██╔══██╗██╔══██╗████╗ ████║██║████╗  ██║
██║  ███╗███████║██████╔╝██╔████╔██║██║██╔██╗ ██║
██║   ██║██╔══██║██╔══██╗██║╚██╔╝██║██║██║╚██╗██║
╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║██║██║ ╚████║
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝
        R O U T I N E
```

**Garmin Connect + Claude API → rutina semanal personalizada de running y gym**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Garmin](https://img.shields.io/badge/Garmin-Connect-007CC3?style=flat&logo=garmin&logoColor=white)](https://connect.garmin.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

</div>

---

## ¿Qué hace?

Conecta con tu cuenta de **Garmin Connect**, extrae tus métricas de las últimas semanas y usa **Claude** para generar una rutina de 7 días adaptada exactamente a tu estado actual — no una plantilla genérica.

```
Garmin Connect
  └─ HRV, sueño, training load, VO2 max
  └─ Historial de actividades (running + gym)
  └─ Body battery, resting HR, stress score
        │
        ▼
  Claude Opus 4.6
  └─ Polarized training 80/20 (Seiler & Kjerland, 2006)
  └─ Concurrent training science (Wilson et al., 2012)
  └─ HRV-guided periodization (Buchheit & Plews)
        │
        ▼
  rutina_YYYY-MM-DD.md
  └─ Plan de 7 días con running + gym
  └─ Justificación basada en tus datos reales
  └─ Alertas y ajustes dinámicos por HRV
```

---

## Requisitos

- Python 3.9+
- Cuenta de [Garmin Connect](https://connect.garmin.com)
- API Key de [Anthropic](https://console.anthropic.com)

---

## Instalación

```bash
git clone https://github.com/santtisosa/garmin-routine.git
cd garmin-routine
pip install -r requirements.txt
cp .env.example .env
```

Editar `.env` con tus credenciales:

```env
GARMIN_EMAIL=tu@email.com
GARMIN_PASSWORD=tu_password_garmin
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Uso

### 1. Configurar tu perfil

Editar el bloque `USER_PROFILE` al final de `routine.py`:

```python
USER_PROFILE = {
    "nombre": "Santiago",
    "objetivo_principal": "mejorar rendimiento en 10K / media maratón",
    "objetivo_gym": "hipertrofia moderada y fuerza de base",
    "dias_disponibles": 6,
    "experiencia_running": "intermedio",   # principiante / intermedio / avanzado
    "experiencia_gym": "intermedio",
    "lesiones_o_limitaciones": "ninguna",  # o detallar
    "proxima_competencia": None,           # ej: "10K en 6 semanas"
    "weeks_back": 4,                       # semanas de historial a analizar
}
```

### 2. Ejecutar

```bash
python routine.py
```

### 3. Output

El script genera dos archivos:

| Archivo | Contenido |
|---|---|
| `rutina_YYYY-MM-DD.md` | Plan semanal completo con justificaciones |
| `garmin_data.json` | Raw data de Garmin (útil para debug) |

Ejemplo de output:

```
============================================================
  GENERADOR DE RUTINA PERSONALIZADA — Garmin + Claude
============================================================
✓ Conectado a Garmin Connect
✓ 24 actividades obtenidas
✓ HRV obtenido — estado: BALANCED
✓ Training status obtenido (VO2 max: 52.4)
✓ Sueño: 7 noches

⏳ Generando rutina con Claude...

## Lunes — Fuerza (Piernas)
**Objetivo:** Estímulo de fuerza sin comprometer el rodaje del martes...
...
✓ Rutina guardada en rutina_2026-04-13.md
```

---

## Base científica

El prompt embebe los principios clave de tres papers de referencia:

| Paper | Principio aplicado |
|---|---|
| Seiler & Kjerland (2006) | 80% volumen en zona 1, 20% alta intensidad |
| Wilson et al. (2012) | Orden y frecuencia óptima de running + fuerza |
| Buchheit & Plews | HRV como modulador de intensidad diaria |

---

## Nota sobre Garmin 2FA

Si tu cuenta tiene verificación en dos pasos, la librería `garminconnect` lo maneja automáticamente — te pedirá el código MFA por consola la primera vez. Las sesiones se cachean localmente.

---

## Licencia

MIT
