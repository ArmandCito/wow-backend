from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require
from business.views import PUBLIC_CACHE
from core.schema import errors

from . import services
from .models import Campaign
from .serializers import CampaignSerializer, PromotionSerializer


class PromotionListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Homepage promotions shown right now",
        parameters=[OpenApiParameter("placement", enum=["home-offers", "home-hero"])],
        responses={200: PromotionSerializer(many=True)},
    )
    def get(self, request):
        campaigns = Campaign.objects.live().select_related("cta_category")
        if request.query_params.get("placement"):
            campaigns = campaigns.filter(placement=request.query_params["placement"])
        response = Response(PromotionSerializer(campaigns, many=True).data)
        response["Cache-Control"] = PUBLIC_CACHE
        return response


def get_campaign(slug):
    return get_object_or_404(Campaign.objects.select_related("cta_category"), slug=slug)


class CampaignListView(APIView):
    permission_classes = [require("ads:manage")]

    @extend_schema(summary="All campaigns (portal)", responses={200: CampaignSerializer(many=True), **errors(401, 403)})
    def get(self, request):
        return Response(CampaignSerializer(Campaign.objects.select_related("cta_category"), many=True).data)

    @extend_schema(summary="Create a campaign (draft)", request=CampaignSerializer,
                   responses={201: CampaignSerializer, **errors(401, 403, 422)})
    def post(self, request):
        serializer = CampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save(status=Campaign.Status.DRAFT, created_by=request.user)
        services.audit(request.user, campaign, "saved")
        return Response(CampaignSerializer(campaign).data, status=status.HTTP_201_CREATED)


class CampaignDetailView(APIView):
    permission_classes = [require("ads:manage")]

    @extend_schema(summary="One campaign", responses={200: CampaignSerializer, **errors(401, 403, 404)})
    def get(self, request, slug):
        return Response(CampaignSerializer(get_campaign(slug)).data)

    @extend_schema(
        summary="Edit a campaign",
        description="Editing a live (scheduled/published/paused) campaign also needs `content:publish`.",
        request=CampaignSerializer,
        responses={200: CampaignSerializer, **errors(401, 403, 404, 422)},
    )
    def patch(self, request, slug):
        campaign = get_campaign(slug)
        services.check_can_edit(request.user, campaign)
        serializer = CampaignSerializer(campaign, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()
        services.refresh_status(campaign)
        services.audit(request.user, campaign, "saved" if campaign.status == Campaign.Status.DRAFT else "updated")
        return Response(CampaignSerializer(campaign).data)

    @extend_schema(summary="Delete a draft", responses={204: None, **errors(401, 403, 404, 409)})
    def delete(self, request, slug):
        services.delete(request.user, get_campaign(slug))
        return Response(status=status.HTTP_204_NO_CONTENT)


def action_view(action, permission, summary, description=""):
    class CampaignActionView(APIView):
        permission_classes = [require(permission)]

        @extend_schema(summary=summary, description=description, request=None,
                       responses={200: CampaignSerializer, **errors(401, 403, 404, 409)})
        def post(self, request, slug):
            campaign = action(request.user, get_campaign(slug))
            return Response(CampaignSerializer(campaign).data)

    CampaignActionView.__name__ = f"Campaign{action.__name__.title().replace('_', '')}View"
    return CampaignActionView


CampaignPublishView = action_view(
    services.publish, "content:publish", "Publish a campaign",
    "Becomes `scheduled` when `startsAt` is in the future, `published` otherwise.",
)
CampaignPauseView = action_view(services.pause, "ads:manage", "Pause a campaign")
CampaignResumeView = action_view(services.resume, "ads:manage", "Resume a paused campaign")
CampaignCancelScheduleView = action_view(services.cancel_schedule, "ads:manage", "Cancel a schedule (back to draft)")
