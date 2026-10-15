from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import IsClient, require
from business.models import BusinessSettings
from core.errors import ValidationFailed
from core.schema import errors
from core.throttles import VisitorRateThrottle
from core.time import start_of_kigali_day

from . import services
from .models import ACTIVE_STAGES, Order, Stage
from .serializers import (
    AssignSerializer,
    OrderEnvelopeSerializer,
    OrderSerializer,
    PaymentUpdateSerializer,
    PlaceOrderSerializer,
    StaffOrderEnvelopeSerializer,
    StaffOrderSerializer,
    TransitionSerializer,
)

ORDER_ID = r"(?P<order_id>[A-Za-z]+-\d+)"


def search(orders, query):
    """Order id, client code, customer name or phone."""
    query = (query or "").strip()
    if not query:
        return orders
    return orders.filter(
        Q(id__in=Order.objects.by_public_id(query).values("id"))
        | Q(client__client_code__iexact=query)
        | Q(contact_name__icontains=query)
        | Q(contact_phone__icontains=query)
    )


class OrdersView(APIView):
    """POST: checkout (client or guest). GET: the register queue (staff)."""

    throttle_scope = "place_order"

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "POST" else [require("orders:process")()]

    def get_throttles(self):
        return [VisitorRateThrottle()] if self.request.method == "POST" else []

    @extend_schema(
        summary="Place an order (signed-in client, or guest without a token)",
        description="The server recomputes every price from the menu. Guests send `contact.name` and "
        "`contact.phone`. `409 item_unavailable` lists `details.itemIds`.",
        request=PlaceOrderSerializer,
        responses={201: OrderEnvelopeSerializer, **errors(401, 403, 409, 422, 429)},
    )
    def post(self, request):
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        order = services.place_order(user, serializer.validated_data)
        return Response({"order": OrderSerializer(order).data}, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Register queue (staff)",
        parameters=[
            OpenApiParameter("since", str, description="ISO date. Default: start of the register window (3 days)."),
            OpenApiParameter("stage", str, description="One stage or several, comma separated. `active` = not finished."),
            OpenApiParameter("managerId", str),
            OpenApiParameter("guest", bool),
            OpenApiParameter("q", str, description="Order id, client code, name or phone"),
        ],
        responses={200: StaffOrderSerializer(many=True), **errors(401, 403, 422)},
    )
    def get(self, request):
        params = request.query_params
        orders = Order.objects.with_lines()

        if params.get("since"):
            since = parse_datetime(params["since"])
            if since is None:
                raise ValidationFailed(details={"since": "invalid"})
        else:
            since = start_of_kigali_day(BusinessSettings.load().queue_window_days - 1)
        orders = orders.filter(placed_at__gte=since)

        if params.get("stage"):
            stages = set(params["stage"].split(","))
            if "active" in stages:
                stages = (stages - {"active"}) | set(ACTIVE_STAGES)
            orders = orders.filter(stage__in=stages & set(Stage.values))
        if params.get("managerId"):
            orders = orders.filter(manager__staff_id=params["managerId"])
        if params.get("guest") in ("true", "false"):
            orders = orders.filter(guest=params["guest"] == "true")
        orders = search(orders, params.get("q"))
        return Response(StaffOrderSerializer(orders[:500], many=True).data)


class StaffOrderDetailView(APIView):
    permission_classes = [require("orders:process")]

    @extend_schema(summary="One order (staff)", responses={200: StaffOrderSerializer, **errors(401, 403, 404)})
    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.with_lines().by_public_id(order_id))
        return Response(StaffOrderSerializer(order).data)


class OrderTransitionView(APIView):
    permission_classes = [require("orders:process")]

    @extend_schema(
        summary="Move an order to its next stage",
        description="new → accepted → preparing → ready → completed; new|accepted → cancelled. "
        "Completing a pay-on-pickup order marks it paid; cancelling marks it not charged. "
        "Notifies the client and records an audit event.",
        request=TransitionSerializer,
        responses={200: StaffOrderEnvelopeSerializer, **errors(401, 403, 404, 409, 422)},
    )
    def post(self, request, order_id):
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition(order_id, serializer.validated_data["to"], request.user)
        return Response({"order": _staff_order(order_id)})


class OrderPaymentView(APIView):
    permission_classes = [require("orders:process")]

    @extend_schema(summary="Confirm the payment (Mobile Money checked by staff)", request=PaymentUpdateSerializer,
                   responses={200: StaffOrderEnvelopeSerializer, **errors(401, 403, 404, 409, 422)})
    def post(self, request, order_id):
        PaymentUpdateSerializer(data=request.data).is_valid(raise_exception=True)
        services.confirm_payment(order_id, request.user)
        return Response({"order": _staff_order(order_id)})


class OrderAssignView(APIView):
    permission_classes = [require("managers:manage")]

    @extend_schema(summary="Give the order to another manager (superadmin)", request=AssignSerializer,
                   responses={200: StaffOrderEnvelopeSerializer, **errors(401, 403, 404, 422)})
    def post(self, request, order_id):
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.assign(order_id, serializer.validated_data["manager_id"], request.user)
        return Response({"order": _staff_order(order_id)})


def _staff_order(order_id):
    return StaffOrderSerializer(Order.objects.with_lines().by_public_id(order_id).get()).data


# ───────── Client area ─────────

STATUS_FILTERS = {
    "active": Q(stage__in=ACTIVE_STAGES),
    "completed": Q(stage=Stage.COMPLETED),
    "cancelled": Q(stage=Stage.CANCELLED),
}


class MyOrdersView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        summary="My orders, newest first",
        parameters=[
            OpenApiParameter("status", enum=["active", "completed", "cancelled"]),
            OpenApiParameter("q", str, description="Order id, e.g. ORD-10"),
        ],
        responses={200: OrderSerializer(many=True), **errors(401, 403)},
    )
    def get(self, request):
        orders = Order.objects.with_lines().filter(client=request.user)
        if request.query_params.get("status") in STATUS_FILTERS:
            orders = orders.filter(STATUS_FILTERS[request.query_params["status"]])
        query = request.query_params.get("q", "").strip().upper()
        if query:
            number = query.removeprefix("ORD-").removeprefix("ORD")
            orders = [order for order in orders if number in order.public_id]
        return Response(OrderSerializer(orders, many=True).data)


class MyOrderDetailView(APIView):
    permission_classes = [IsClient]

    @extend_schema(summary="One of my orders (404 when it is not mine)",
                   responses={200: OrderSerializer, **errors(401, 403, 404)})
    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.with_lines().filter(client=request.user).by_public_id(order_id))
        return Response(OrderSerializer(order).data)
