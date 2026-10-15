from django.db import connection
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require

from .schema import errors
from .uploads import store_image


def health(request):
    """Render health check: the app answers and the database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})


class UploadView(APIView):
    permission_classes = [require("menu:edit", "ads:manage", any_of=True)]
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Upload an image (menu photo, campaign visual)",
        description="Multipart field `file`: JPEG, PNG or WebP, 5 MB max. Resized to 1600 px max. "
        "Use the returned `imageId` in a menu item or a campaign.",
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={201: inline_serializer("Upload", {"imageId": serializers.UUIDField(), "url": serializers.URLField()}),
                   **errors(401, 403, 422)},
    )
    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            raise serializers.ValidationError({"file": serializers.ErrorDetail("Send the image in `file`.", "required")})
        upload = store_image(file, user=request.user, request=request)
        return Response({"image_id": upload.id, "url": upload.url}, status=status.HTTP_201_CREATED)
