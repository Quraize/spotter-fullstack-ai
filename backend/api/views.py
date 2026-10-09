from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView


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
