"""Request validation for POST /api/plan."""

from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

from .planner import PlanRequest

SAMPLE_INTERVALS_MILES = (10, 25, 50)
MAX_DEPARTURE_DAYS_AHEAD = 14  # inside Open-Meteo's 16-day horizon with room for the trip
MAX_DEPARTURE_HOURS_PAST = 1
MAX_LOAD_LB = 200_000


class PlanRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(min_length=2, max_length=200)
    destination = serializers.CharField(min_length=2, max_length=200)
    departure_time = serializers.CharField(max_length=40)
    load_weight_lb = serializers.FloatField(min_value=1, max_value=MAX_LOAD_LB)
    sample_interval_miles = serializers.ChoiceField(choices=SAMPLE_INTERVALS_MILES)

    def validate_departure_time(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use ISO 8601, for example 2026-10-11T08:00:00-05:00.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise serializers.ValidationError("Include a UTC offset, for example -05:00.")
        now = timezone.now()
        if parsed < now - timedelta(hours=MAX_DEPARTURE_HOURS_PAST):
            raise serializers.ValidationError("Departure time is in the past.")
        if parsed > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within the next {MAX_DEPARTURE_DAYS_AHEAD} days (forecast horizon)."
            )
        return parsed

    def to_plan_request(self) -> PlanRequest:
        data = self.validated_data
        return PlanRequest(
            origin=data["origin"],
            destination=data["destination"],
            departure_time=data["departure_time"],
            load_weight_lb=float(data["load_weight_lb"]),
            sample_interval_miles=int(data["sample_interval_miles"]),
        )
