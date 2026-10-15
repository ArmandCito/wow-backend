from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import IsClient
from core.schema import errors
from core.time import now

from .models import ClientNotification
from .serializers import ClientNotificationSerializer, MarkReadSerializer


class NotificationListView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        summary="My order updates, newest first",
        parameters=[OpenApiParameter("unread", bool, description="true = unread only")],
        responses={200: ClientNotificationSerializer(many=True), **errors(401, 403)},
    )
    def get(self, request):
        notifications = ClientNotification.objects.filter(client=request.user).select_related("client", "order")
        if request.query_params.get("unread") == "true":
            notifications = notifications.filter(read_at__isnull=True)
        return Response(ClientNotificationSerializer(notifications[:100], many=True).data)


class NotificationReadView(APIView):
    permission_classes = [IsClient]

    @extend_schema(summary="Mark notifications as read: `{ids: [...]}` or `{all: true}`",
                   request=MarkReadSerializer, responses={204: None, **errors(401, 403, 422)})
    def post(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unread = ClientNotification.objects.filter(client=request.user, read_at__isnull=True)
        if not serializer.validated_data["all"]:
            ids = [value for value in serializer.validated_data["ids"] if value.isdigit()]
            unread = unread.filter(id__in=ids)
        unread.update(read_at=now())
        return Response(status=status.HTTP_204_NO_CONTENT)
