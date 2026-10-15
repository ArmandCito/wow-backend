from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require
from audit.services import record
from core.schema import errors

from .models import BusinessSettings
from .serializers import BusinessSerializer

PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=600"


class BusinessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Business details, contact and fees (footer, contact page, checkout)",
                   responses={200: BusinessSerializer})
    def get(self, request):
        response = Response(BusinessSerializer(BusinessSettings.load()).data)
        response["Cache-Control"] = PUBLIC_CACHE
        return response


class BusinessAdminView(APIView):
    permission_classes = [require("business:edit")]

    @extend_schema(summary="Business settings (portal)", responses={200: BusinessSerializer, **errors(401, 403)})
    def get(self, request):
        return Response(BusinessSerializer(BusinessSettings.load()).data)

    @extend_schema(summary="Replace the business settings", request=BusinessSerializer,
                   responses={200: BusinessSerializer, **errors(401, 403, 422)})
    def put(self, request):
        return self._save(request, partial=False)

    @extend_schema(summary="Update some business settings", request=BusinessSerializer,
                   responses={200: BusinessSerializer, **errors(401, 403, 422)})
    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, partial):
        serializer = BusinessSerializer(BusinessSettings.load(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        record(
            actor=request.user, scope="content", type="business.updated",
            text=("Business & contact settings updated", "Paramètres de l’établissement et coordonnées mis à jour"),
        )
        return Response(BusinessSerializer(settings).data)
