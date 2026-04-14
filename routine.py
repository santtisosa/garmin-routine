"""
Garmin Connect → Rutina personalizada con IA

Basado en:
- Seiler & Kjerland (2006): Polarized training 80/20
- Wilson et al. (2012): Concurrent training interference
- Buchheit & Plews: HRV-guided periodization

Uso:
    pip install garminconnect anthropic python-dotenv
    cp .env.example .env  # completar con tus credenciales
    python routine.py
"""

import os
import json
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv
import garminconnect
import anthropic

load_dotenv()

TOKEN_STORE   = Path("~/.garmin_tokens").expanduser()
SESSION_FILE  = Path("~/.garmin_session.json").expanduser()

# ─── Conocimiento científico embebido ────────────────────────────────────────

SCIENCE_CONTEXT = """
## Principios científicos de entrenamiento (Running + Gym)

### 1. Distribución de intensidad — Polarized Training (Seiler & Kjerland, 2006)
- 80% del volumen semanal en zona 1 (fácil, < 2 mmol/L lactato, RPE ≤ 5/10)
- 20% en zona 3 (alta intensidad, > 4 mmol/L lactato, RPE ≥ 7/10)
- Zona 2 (threshold) usada con moderación — produce fatiga sin el retorno adaptativo de zona 3
- Atletas que siguen modelo polarizado mejoran más VO2max, TTE y economía de carrera vs threshold-only
- Foco principal: calidad de los estímulos duros, no cantidad

### 2. Concurrent Training — Interferencia running/fuerza (Wilson et al., 2012; meta-análisis 21 estudios)
- Correr + fuerza en el mismo día reduce hipertrofia (effect size: 0.85 vs 1.23 solo fuerza) y potencia (0.55 vs 0.91)
- El running interfiere más que el ciclismo con las adaptaciones de fuerza
- Regla de orden: fuerza ANTES de correr si el objetivo es ganar fuerza muscular
- Si los objetivos son separados: separar sesiones al menos 6 horas, o días distintos
- Frecuencia y duración del cardio son los principales moderadores de la interferencia

### 3. Entrenamiento guiado por HRV (Buchheit & Plews; ScienceDirect 2021)
- HRV por encima del baseline (media móvil 7 días ± SWC): ok para sesión dura
- HRV por debajo del baseline: bajar intensidad, sesión suave o descanso
- HRV guiado produce mejores resultados en VO2max que periodización fija, con menor carga total
- Body Battery de Garmin y HRV Status son proxies válidos para este modelo

### 4. Periodización running/fuerza combinada
- Semana con carga alta de running → reducir volumen e intensidad de gym
- Priorizar fuerza de piernas (sentadilla, peso muerto, prensa) para economía de carrera
- Core y cadena posterior mejoran economía de carrera (~2-4%)
- No hacer sesión de piernas pesada el día anterior a rodaje largo o intervalos
- Tapering: reducir volumen 30-50% pero mantener intensidad en la semana previa a competencia

### 5. Estructura semanal recomendada (base)
- Lunes: Fuerza (piernas/full body)
- Martes: Rodaje suave (zona 1)
- Miércoles: Intervalos (zona 3) — o descanso según HRV
- Jueves: Fuerza (upper/core)
- Viernes: Rodaje suave o descanso
- Sábado: Rodaje largo (zona 1, >60 min)
- Domingo: Descanso activo o movilidad
"""

# ─── Extractor de datos Garmin ────────────────────────────────────────────────


class GarminFetcher:
    def __init__(self):
        token_file = TOKEN_STORE / "garmin_tokens.json"

        if token_file.exists():
            # Token cacheado de login previo
            self.client = garminconnect.Garmin()
            self.client.login(tokenstore=str(TOKEN_STORE))
            print("✓ Conectado a Garmin Connect (token cacheado)")

        elif SESSION_FILE.exists():
            # Cookies del browser (fallback cuando el IP está rate-limited)
            session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            jwt_web   = session.get("jwt_web", "")
            csrf      = session.get("csrf_token", "")
            if not jwt_web:
                raise ValueError(f"jwt_web vacío en {SESSION_FILE}. Ejecutá get_token.py de nuevo.")
            if not csrf:
                raise ValueError(f"csrf_token vacío en {SESSION_FILE}. Ejecutá get_token.py de nuevo.")

            self.client = garminconnect.Garmin()
            # Inyectamos la sesión del browser directamente, sin hacer login
            self.client.client.jwt_web    = jwt_web
            self.client.client.csrf_token = csrf
            print("✓ Conectado a Garmin Connect (sesión del browser)")

        else:
            # Primera vez — login con email/password
            email    = os.getenv("GARMIN_EMAIL")
            password = os.getenv("GARMIN_PASSWORD")
            if not email or not password:
                raise ValueError(
                    "No hay token ni sesión guardada. "
                    "Ejecutá get_token.py o completá GARMIN_EMAIL/PASSWORD en .env"
                )
            TOKEN_STORE.mkdir(parents=True, exist_ok=True)
            self.client = garminconnect.Garmin(
                email, password,
                prompt_mfa=lambda: input("Código MFA de Garmin: "),
            )
            self.client.login(tokenstore=str(TOKEN_STORE))
            print(f"✓ Conectado a Garmin Connect (token guardado en {TOKEN_STORE})")

    def fetch_all(self, weeks: int = 4) -> dict:
        today = date.today()
        start = today - timedelta(weeks=weeks)
        start_str = start.isoformat()
        end_str = today.isoformat()

        data = {}

        # Actividades recientes
        try:
            activities = self.client.get_activities_by_date(start_str, end_str)
            data["activities"] = self._parse_activities(activities)
            print(f"✓ {len(activities)} actividades obtenidas")
        except Exception as e:
            print(f"⚠ Actividades: {e}")
            data["activities"] = []

        # Stats diarias (HRV, resting HR, stress, body battery, sleep)
        try:
            user_summary = self.client.get_user_summary(today.isoformat())
            data["today_summary"] = {
                "resting_hr": user_summary.get("restingHeartRate"),
                "stress_level_avg": user_summary.get("averageStressLevel"),
                "body_battery_highest": user_summary.get("bodyBatteryHighestValue"),
                "body_battery_lowest": user_summary.get("bodyBatteryLowestValue"),
                "steps": user_summary.get("totalSteps"),
                "active_calories": user_summary.get("activeKilocalories"),
            }
            print("✓ Resumen diario obtenido")
        except Exception as e:
            print(f"⚠ Resumen diario: {e}")
            data["today_summary"] = {}

        # HRV Status
        try:
            hrv = self.client.get_hrv_data(today.isoformat())
            data["hrv"] = {
                "last_night": hrv.get("hrvSummary", {}).get("lastNight"),
                "weekly_avg": hrv.get("hrvSummary", {}).get("weeklyAvg"),
                "status": hrv.get("hrvSummary", {}).get("status"),  # BALANCED, UNBALANCED, POOR, LOW
            }
            print("✓ HRV obtenido")
        except Exception as e:
            print(f"⚠ HRV: {e}")
            data["hrv"] = {}

        # VO2 Max y Training Status
        try:
            training_status = self.client.get_training_status(today.isoformat())
            data["training_status"] = {
                "vo2max_running": training_status.get("vo2MaxPreciseValue"),
                "training_load_last7": training_status.get("trainingLoad7DaysAvg"),
                "training_readiness": training_status.get("trainingReadinessScore"),
            }
            print("✓ Training status obtenido")
        except Exception as e:
            print(f"⚠ Training status: {e}")
            data["training_status"] = {}

        # Sleep última semana
        try:
            sleep_data = []
            for i in range(7):
                d = (today - timedelta(days=i)).isoformat()
                try:
                    s = self.client.get_sleep_data(d)
                    summary = s.get("dailySleepDTO", {})
                    sleep_data.append({
                        "date": d,
                        "duration_hours": round((summary.get("sleepTimeSeconds") or 0) / 3600, 1),
                        "score": summary.get("sleepScores", {}).get("overall", {}).get("value"),
                        "deep_sleep_hours": round((summary.get("deepSleepSeconds") or 0) / 3600, 1),
                        "rem_hours": round((summary.get("remSleepSeconds") or 0) / 3600, 1),
                    })
                except Exception as e:
                    print(f"⚠ Sueño {d}: {e}")
            data["sleep_last7"] = sleep_data
            print(f"✓ Datos de sueño: {len(sleep_data)} noches")
        except Exception as e:
            print(f"⚠ Sueño: {e}")
            data["sleep_last7"] = []

        return data

    def _parse_activities(self, activities: list) -> list:
        parsed = []
        for a in activities[:30]:  # máximo 30 para no inflar el prompt
            parsed.append({
                "date": a.get("startTimeLocal", "")[:10],
                "type": a.get("activityType", {}).get("typeKey", "unknown"),
                "name": a.get("activityName", ""),
                "distance_km": round((a.get("distance") or 0) / 1000, 2),
                "duration_min": round((a.get("duration") or 0) / 60, 1),
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "avg_pace_min_km": self._speed_to_pace(a.get("averageSpeed")),
                "training_load": a.get("activityTrainingLoad"),
                "aerobic_te": a.get("aerobicTrainingEffect"),
                "anaerobic_te": a.get("anaerobicTrainingEffect"),
                "calories": a.get("calories"),
            })
        return parsed

    def _speed_to_pace(self, speed_ms) -> str | None:
        if not speed_ms or speed_ms == 0:
            return None
        pace_s = 1000 / speed_ms
        mins = int(pace_s // 60)
        secs = int(pace_s % 60)
        return f"{mins}:{secs:02d} min/km"


# ─── Generador de rutina ─────────────────────────────────────────────────────

class RoutineGenerator:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Falta ANTHROPIC_API_KEY en .env")
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, garmin_data: dict, user_profile: dict) -> str:
        prompt = self._build_prompt(garmin_data, user_profile)

        print("\n⏳ Generando rutina...\n")
        model = os.getenv("AI_MODEL", "claude-opus-4-6")
        message = self.client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _build_prompt(self, data: dict, profile: dict) -> str:
        return f"""Eres un entrenador de alto rendimiento especializado en running y fuerza funcional.
Tienes acceso a los datos reales del atleta de Garmin Connect y a evidencia científica actualizada.

Tu tarea: generar una rutina semanal PERSONALIZADA y detallada para las próximas 7 días.

---

## PERFIL DEL ATLETA
{json.dumps(profile, indent=2, ensure_ascii=False)}

---

## DATOS GARMIN (últimas {profile.get('weeks_back', 4)} semanas)

### Estado hoy
{json.dumps(data.get('today_summary', {}), indent=2, ensure_ascii=False)}

### HRV y recuperación
{json.dumps(data.get('hrv', {}), indent=2, ensure_ascii=False)}

### Training Status (VO2 max, carga)
{json.dumps(data.get('training_status', {}), indent=2, ensure_ascii=False)}

### Sueño últimos 7 días
{json.dumps(data.get('sleep_last7', []), indent=2, ensure_ascii=False)}

### Historial de actividades recientes
{json.dumps(data.get('activities', []), indent=2, ensure_ascii=False)}

---

## BASE CIENTÍFICA
{SCIENCE_CONTEXT}

---

## INSTRUCCIONES

1. Analiza primero el estado de recuperación actual (HRV, body battery, sueño, training load).
2. Identifica el patrón de entrenamiento de las últimas semanas (volumen, intensidad, tipos de sesión).
3. Detecta desequilibrios (ej: demasiados días duros seguidos, poco volumen zona 1, gym vs running mal distribuido).
4. Genera la rutina de 7 días aplicando los principios científicos.

## FORMATO DE SALIDA

Para cada día incluye:
- **Tipo de sesión** y objetivo fisiológico
- **Detalles de running** (zona, distancia/tiempo, RPE, pace orientativo)
- **Detalles de gym** (ejercicios, series, reps, carga orientativa, notas técnicas)
- **Por qué hoy** (justificación basada en los datos Garmin del atleta)

Al final agrega:
- Resumen de carga semanal (km totales, sesiones de fuerza, distribución zona 1/zona 3)
- 3 alertas o cosas a monitorear basadas en los datos actuales
- Ajuste sugerido si el HRV baja o sube significativamente durante la semana

Sé específico y práctico. No des rutinas genéricas — cada decisión debe estar justificada por los datos reales del atleta.
"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Perfil manual del atleta (editar según corresponda)
    USER_PROFILE = {
        "nombre": "Santiago",
        "objetivo_principal": "mejorar rendimiento en running (10K/media maratón) manteniendo fuerza funcional",
        "objetivo_gym": "hipertrofia moderada y fuerza de base, no máxima musculatura",
        "dias_disponibles": 6,  # días por semana para entrenar
        "experiencia_running": "intermedio",  # principiante / intermedio / avanzado
        "experiencia_gym": "intermedio",
        "lesiones_o_limitaciones": "ninguna",  # o detallar
        "proxima_competencia": None,  # ej: "10K en 6 semanas"
        "weeks_back": 4,  # cuántas semanas de historial analizar
    }

    print("=" * 60)
    print("  GENERADOR DE RUTINA PERSONALIZADA — Garmin")
    print("=" * 60)

    # 1. Obtener datos de Garmin
    fetcher = GarminFetcher()
    garmin_data = fetcher.fetch_all(weeks=USER_PROFILE["weeks_back"])

    # Guardar raw data para debug
    with open("garmin_data.json", "w", encoding="utf-8") as f:
        json.dump(garmin_data, f, indent=2, ensure_ascii=False, default=str)
    print("✓ Datos guardados en garmin_data.json")

    # 2. Generar rutina
    generator = RoutineGenerator()
    routine = generator.generate(garmin_data, USER_PROFILE)

    # 3. Guardar y mostrar resultado
    output_file = f"rutina_{date.today().isoformat()}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Rutina Personalizada — {date.today().isoformat()}\n\n")
        f.write(routine)

    print("\n" + "=" * 60)
    print(routine)
    print("=" * 60)
    print(f"\n✓ Rutina guardada en {output_file}")


if __name__ == "__main__":
    main()
