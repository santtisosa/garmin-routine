import json
import os
from unittest.mock import MagicMock, patch

import pytest

# RoutineGenerator requires ANTHROPIC_API_KEY at import time via __init__,
# so we patch the env var before instantiating it in each test.
import routine
from routine import GarminFetcher, RoutineGenerator


# ─── GarminFetcher._speed_to_pace ────────────────────────────────────────────

class TestSpeedToPace:
    def setup_method(self):
        # Bypass __init__ — we only need the pure helper method
        self.fetcher = object.__new__(GarminFetcher)

    def test_none_returns_none(self):
        assert self.fetcher._speed_to_pace(None) is None

    def test_zero_returns_none(self):
        assert self.fetcher._speed_to_pace(0) is None

    def test_typical_easy_run(self):
        # 3.0 m/s → 1000/3 = 333.3 s/km → 5:33 min/km
        assert self.fetcher._speed_to_pace(3.0) == "5:33 min/km"

    def test_threshold_pace(self):
        # 3.333 m/s → 300 s/km → 5:00 min/km
        assert self.fetcher._speed_to_pace(1000 / 300) == "5:00 min/km"

    def test_fast_interval(self):
        # 4.0 m/s → 250 s/km → 4:10 min/km
        assert self.fetcher._speed_to_pace(4.0) == "4:10 min/km"

    def test_seconds_zero_padded(self):
        # 1000/65 ≈ 15.38 s/km → 0:15 min/km (edge case: sub-minute pace)
        result = self.fetcher._speed_to_pace(1000 / 65)
        assert result.endswith("min/km")
        mins, secs = result.replace(" min/km", "").split(":")
        assert len(secs) == 2  # always two digits


# ─── GarminFetcher._parse_activities ─────────────────────────────────────────

class TestParseActivities:
    def setup_method(self):
        self.fetcher = object.__new__(GarminFetcher)

    def _make_activity(self, **overrides):
        base = {
            "startTimeLocal": "2026-04-10T07:30:00",
            "activityType": {"typeKey": "running"},
            "activityName": "Rodaje suave",
            "distance": 10000,        # 10 km in meters
            "duration": 3600,         # 60 min in seconds
            "averageHR": 145,
            "maxHR": 165,
            "averageSpeed": 2.778,    # ~6:00 min/km
            "activityTrainingLoad": 80,
            "aerobicTrainingEffect": 3.5,
            "anaerobicTrainingEffect": 1.2,
            "calories": 550,
        }
        base.update(overrides)
        return base

    def test_basic_fields(self):
        parsed = self.fetcher._parse_activities([self._make_activity()])
        assert len(parsed) == 1
        a = parsed[0]
        assert a["date"] == "2026-04-10"
        assert a["type"] == "running"
        assert a["name"] == "Rodaje suave"
        assert a["distance_km"] == 10.0
        assert a["duration_min"] == 60.0
        assert a["avg_hr"] == 145
        assert a["max_hr"] == 165
        assert a["calories"] == 550

    def test_empty_list(self):
        assert self.fetcher._parse_activities([]) == []

    def test_truncates_at_30(self):
        activities = [self._make_activity() for _ in range(50)]
        parsed = self.fetcher._parse_activities(activities)
        assert len(parsed) == 30

    def test_missing_optional_fields_default_to_none_or_zero(self):
        a = self.fetcher._parse_activities([{
            "startTimeLocal": "2026-04-10T08:00:00",
            "activityType": {},
            "activityName": "",
        }])[0]
        assert a["distance_km"] == 0.0
        assert a["duration_min"] == 0.0
        assert a["avg_hr"] is None
        assert a["type"] == "unknown"

    def test_pace_computed_from_speed(self):
        activity = self._make_activity(averageSpeed=1000 / 300)  # 5:00 min/km
        parsed = self.fetcher._parse_activities([activity])
        assert parsed[0]["avg_pace_min_km"] == "5:00 min/km"

    def test_no_speed_gives_no_pace(self):
        activity = self._make_activity(averageSpeed=None)
        parsed = self.fetcher._parse_activities([activity])
        assert parsed[0]["avg_pace_min_km"] is None


# ─── RoutineGenerator._build_prompt ──────────────────────────────────────────

class TestBuildPrompt:
    def setup_method(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                self.generator = RoutineGenerator()

    def _profile(self, **overrides):
        base = {
            "nombre": "Test",
            "objetivo_principal": "mejorar 10K",
            "objetivo_gym": "fuerza",
            "dias_disponibles": 5,
            "experiencia_running": "intermedio",
            "experiencia_gym": "principiante",
            "lesiones_o_limitaciones": "ninguna",
            "proxima_competencia": None,
            "weeks_back": 4,
        }
        base.update(overrides)
        return base

    def _garmin_data(self):
        return {
            "today_summary": {"resting_hr": 52, "body_battery_highest": 85},
            "hrv": {"last_night": 62, "status": "BALANCED"},
            "training_status": {"vo2max_running": 51.0},
            "sleep_last7": [{"date": "2026-04-10", "duration_hours": 7.5}],
            "activities": [],
        }

    def test_prompt_is_string(self):
        prompt = self.generator._build_prompt(self._garmin_data(), self._profile())
        assert isinstance(prompt, str)

    def test_prompt_contains_profile_data(self):
        profile = self._profile(nombre="Santiago")
        prompt = self.generator._build_prompt(self._garmin_data(), profile)
        assert "Santiago" in prompt

    def test_prompt_contains_hrv_data(self):
        data = self._garmin_data()
        prompt = self.generator._build_prompt(data, self._profile())
        assert "BALANCED" in prompt

    def test_prompt_contains_science_context(self):
        prompt = self.generator._build_prompt(self._garmin_data(), self._profile())
        assert "Seiler" in prompt
        assert "Wilson" in prompt

    def test_weeks_back_reflected_in_prompt(self):
        profile = self._profile(weeks_back=8)
        prompt = self.generator._build_prompt(self._garmin_data(), profile)
        assert "8" in prompt

    def test_missing_garmin_sections_dont_crash(self):
        prompt = self.generator._build_prompt({}, self._profile())
        assert isinstance(prompt, str)


# ─── RoutineGenerator.generate ───────────────────────────────────────────────

class TestGenerate:
    def setup_method(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic"):
                self.generator = RoutineGenerator()

    def test_returns_api_response_text(self):
        fake_text = "## Lunes\nFuerza de piernas..."
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=fake_text)]
        self.generator.client.messages.create.return_value = mock_message

        result = self.generator.generate(
            {"activities": [], "hrv": {}, "today_summary": {}, "training_status": {}, "sleep_last7": []},
            {"nombre": "Test", "weeks_back": 4},
        )
        assert result == fake_text

    def test_api_called_with_model_from_env(self):
        fake_text = "rutina"
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=fake_text)]
        self.generator.client.messages.create.return_value = mock_message

        with patch.dict(os.environ, {"AI_MODEL": "test-model-x"}):
            self.generator.generate({}, {"weeks_back": 4})

        call_kwargs = self.generator.client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "test-model-x"

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                RoutineGenerator()
