import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from providers.errors import ProviderError

from .planner import PlanningError
from .serializers import PlanRequestSerializer
from .services import get_planner

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness check used by the frontend, Docker, and deployment smoke tests."""

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "spotter-routing-api",
                "time": timezone.now().isoformat(),
                "tomtom_key_configured": bool(settings.TOMTOM_API_KEY),
            }
        )


class PlanView(APIView):
    """
    POST /api/plan

    Body: origin, destination, departure_time (ISO 8601 with offset),
    load_weight_lb, sample_interval_miles (10 | 25 | 50).
    Returns routes with checkpoints, risk summaries, the recommendation and
    the heatmap grid. Errors are {"error": {"code", "message", "fields"?}}.
    """

    def post(self, request):
        serializer = PlanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": {"code": "validation_error", "message": "Invalid request.", "fields": serializer.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            plan = get_planner().plan(serializer.to_plan_request())
        except (ProviderError, PlanningError) as exc:
            logger.warning("plan request failed: %s: %s", exc.code, exc.message)
            return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.http_status)
        return Response(plan)
