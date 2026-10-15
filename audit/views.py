from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require
from core.schema import errors

from .models import AuditEvent
from .serializers import AuditEventSerializer, AuditPageSerializer


class AuditListView(APIView):
    permission_classes = [require("overview:view")]

    @extend_schema(
        summary="Audit trail, newest first",
        parameters=[
            OpenApiParameter("scope", enum=["orders", "content", "access"]),
            OpenApiParameter("limit", int, description="1–100, default 20"),
            OpenApiParameter("cursor", str, description="`nextCursor` of the previous page"),
        ],
        responses={200: AuditPageSerializer, **errors(401, 403)},
    )
    def get(self, request):
        events = AuditEvent.objects.select_related("actor", "target")
        scope = request.query_params.get("scope")
        if scope in AuditEvent.Scope.values:
            events = events.filter(scope=scope)
        cursor = request.query_params.get("cursor", "")
        if cursor.isdigit():
            events = events.filter(id__lt=int(cursor))
        limit = request.query_params.get("limit", "20")
        limit = min(max(int(limit), 1), 100) if limit.isdigit() else 20

        page = list(events[: limit + 1])
        more = len(page) > limit
        page = page[:limit]
        return Response(
            {
                "items": AuditEventSerializer(page, many=True).data,
                "next_cursor": str(page[-1].id) if more else None,
            }
        )
