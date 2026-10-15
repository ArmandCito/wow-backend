from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require
from accounts.models import Duty, Role, Status, User
from accounts.serializers import ContentGrantInputSerializer, ContentGrantSerializer
from business.models import BusinessSettings
from core.schema import errors
from core.time import start_of_kigali_day
from orders.models import ACTIVE_STAGES, Order, PaymentStatus, Stage
from orders.serializers import OverviewSerializer

from . import services
from .serializers import InvitationSerializer, ManagerUpdateSerializer, StaffMemberSerializer

MANAGE = [require("managers:manage")]


def get_manager(staff_id):
    return get_object_or_404(services.managers(), staff_id=staff_id)


def manager_response(staff_id):
    return Response(StaffMemberSerializer(get_manager(staff_id)).data)


class ManagerListView(APIView):
    permission_classes = MANAGE

    @extend_schema(
        summary="Manager directory",
        parameters=[
            OpenApiParameter("status", enum=["active", "suspended", "invited"]),
            OpenApiParameter("q", str, description="Name, email or assignment"),
        ],
        responses={200: StaffMemberSerializer(many=True), **errors(401, 403)},
    )
    def get(self, request):
        managers = services.managers()
        if request.query_params.get("status") in Status.values:
            managers = managers.filter(status=request.query_params["status"])
        query = request.query_params.get("q", "").strip()
        if query:
            managers = managers.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(assignment__icontains=query))
        return Response(StaffMemberSerializer(managers, many=True).data)


class ManagerDetailView(APIView):
    permission_classes = MANAGE

    @extend_schema(summary="One manager", responses={200: StaffMemberSerializer, **errors(401, 403, 404)})
    def get(self, request, staff_id):
        return manager_response(staff_id)

    @extend_schema(summary="Rename, change duty or assignment", request=ManagerUpdateSerializer,
                   responses={200: StaffMemberSerializer, **errors(401, 403, 404, 409, 422)})
    def patch(self, request, staff_id):
        serializer = ManagerUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_manager(request.user, get_manager(staff_id), dict(serializer.validated_data))
        return manager_response(staff_id)


class ManagerSuspendView(APIView):
    permission_classes = MANAGE

    @extend_schema(
        summary="Suspend a manager",
        description="Refused at once on every request, signed out, assignment and grant removed; "
        "active orders go to another on-duty manager (or stay unassigned).",
        request=None,
        responses={200: StaffMemberSerializer, **errors(401, 403, 404)},
    )
    def post(self, request, staff_id):
        services.suspend(request.user, get_manager(staff_id))
        return manager_response(staff_id)


class ManagerReactivateView(APIView):
    permission_classes = MANAGE

    @extend_schema(summary="Reactivate a suspended manager", request=None,
                   responses={200: StaffMemberSerializer, **errors(401, 403, 404, 409)})
    def post(self, request, staff_id):
        services.reactivate(request.user, get_manager(staff_id))
        return manager_response(staff_id)


class ManagerGrantView(APIView):
    permission_classes = MANAGE

    @extend_schema(
        summary="Give temporary content rights (replaces the current grant)",
        description="Scopes: food, drinks (edit menu items of that group), labels (NEW badge), ads, publish. "
        "No `expiresAt` = until revoked.",
        request=ContentGrantInputSerializer,
        responses={200: ContentGrantSerializer, **errors(401, 403, 404, 409, 422)},
    )
    def put(self, request, staff_id):
        serializer = ContentGrantInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        grant = services.set_grant(request.user, get_manager(staff_id), **serializer.validated_data)
        return Response(ContentGrantSerializer(grant).data)

    @extend_schema(summary="Revoke the content rights", responses={204: None, **errors(401, 403, 404)})
    def delete(self, request, staff_id):
        services.revoke_grant(request.user, get_manager(staff_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationView(APIView):
    permission_classes = MANAGE

    @extend_schema(
        summary="Invite a manager",
        description="Creates the account (status `invited`) and emails a link to "
        "`{FRONTEND_URL}/{lang}/accept-invitation?token=…` (POST /auth/invitations/accept). "
        "Default access: orders only.",
        request=InvitationSerializer,
        responses={201: StaffMemberSerializer, **errors(401, 403, 409, 422, 503)},
    )
    def post(self, request):
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manager = services.invite(request.user, **serializer.validated_data)
        return Response(StaffMemberSerializer(get_manager(manager.staff_id)).data, status=status.HTTP_201_CREATED)


class InvitationResendView(APIView):
    permission_classes = MANAGE

    @extend_schema(summary="Send the invitation email again (new link)", request=None,
                   responses={204: None, **errors(401, 403, 404, 409, 503)})
    def post(self, request, staff_id):
        services.send_invitation(request.user, get_manager(staff_id), request.data.get("lang", "en"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class OverviewView(APIView):
    permission_classes = [require("overview:view")]

    @extend_schema(summary="Store overview (register window: today and the previous days)",
                   responses={200: OverviewSerializer, **errors(401, 403)})
    def get(self, request):
        window = Order.objects.filter(
            placed_at__gte=start_of_kigali_day(BusinessSettings.load().queue_window_days - 1)
        )
        by_stage = dict(window.values_list("stage").annotate(n=Count("id")))
        completed = window.filter(stage=Stage.COMPLETED).aggregate(value=Sum("total"), count=Count("id"))
        managers = User.objects.filter(role=Role.MANAGER).exclude(status=Status.INVITED)
        active_managers = managers.filter(status=Status.ACTIVE)
        return Response({
            "orders": window.count(),
            "orders_today": window.filter(placed_at__gte=start_of_kigali_day()).count(),
            "active": {stage: by_stage.get(stage, 0) for stage in Stage.values},
            "active_orders": window.filter(stage__in=ACTIVE_STAGES).count(),
            "pending_payments": window.filter(stage__in=ACTIVE_STAGES, payment_status=PaymentStatus.PENDING).count(),
            "completed_value": completed["value"] or 0,
            "completed_count": completed["count"],
            "managers": {
                "active": active_managers.count(),
                "total": managers.count(),
                "on_duty": active_managers.filter(duty=Duty.ON).count(),
                "off_duty": active_managers.filter(duty=Duty.OFF).count(),
                "suspended": managers.filter(status=Status.SUSPENDED).count(),
            },
        })
