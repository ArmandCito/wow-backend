from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import require
from business.views import PUBLIC_CACHE
from core.fields import LOCALIZED_SCHEMA, localized
from core.schema import errors

from . import services
from .models import Category, DrinkSection, MenuItem, OptionChoice, OptionGroup, Tag
from .serializers import (
    AdminMenuItemSerializer,
    CategorySerializer,
    DrinkSectionSerializer,
    MenuItemInputSerializer,
    MenuItemSerializer,
    OptionGroupSerializer,
)

ITEM_FILTERS = [
    OpenApiParameter("group", enum=["food", "drinks"]),
    OpenApiParameter("category", str, description="Category id, e.g. `burgers`"),
    OpenApiParameter("section", str, description="Drink section id, e.g. `mojitos`"),
]


def filter_items(items, params):
    if params.get("group"):
        items = items.filter(group=params["group"])
    if params.get("category"):
        items = items.filter(categories__slug=params["category"])
    if params.get("section"):
        items = items.filter(section__slug=params["section"])
    return items.distinct()


def option_groups():
    available = Prefetch("choices", queryset=OptionChoice.objects.filter(is_available=True), to_attr="available_choices")
    return OptionGroup.objects.prefetch_related(available)


def tags_dict():
    return {tag.key: localized(tag, "label") for tag in Tag.objects.all()}


class PublicCatalogueView(APIView):
    """Read-only catalogue: no token, cacheable."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if response.status_code == 200:
            response["Cache-Control"] = PUBLIC_CACHE
        return response


class CatalogueView(PublicCatalogueView):
    @extend_schema(
        summary="The whole catalogue in one call",
        description="Everything the menu pages need: categories, drink sections, tags, option groups and items.",
        responses={200: inline_serializer("Catalogue", {
            "categories": CategorySerializer(many=True),
            "drinkSections": DrinkSectionSerializer(many=True),
            "tags": serializers.DictField(child=serializers.JSONField()),
            "optionGroups": OptionGroupSerializer(many=True),
            "items": MenuItemSerializer(many=True),
        })},
    )
    def get(self, request):
        return Response({
            "categories": CategorySerializer(Category.objects.filter(is_active=True), many=True).data,
            "drink_sections": DrinkSectionSerializer(DrinkSection.objects.all(), many=True).data,
            "tags": tags_dict(),
            "option_groups": OptionGroupSerializer(option_groups(), many=True).data,
            "items": MenuItemSerializer(MenuItem.objects.public().with_relations(), many=True).data,
        })


class MenuItemListView(PublicCatalogueView):
    @extend_schema(summary="Menu items", parameters=ITEM_FILTERS, responses={200: MenuItemSerializer(many=True)})
    def get(self, request):
        items = filter_items(MenuItem.objects.public().with_relations(), request.query_params)
        return Response(MenuItemSerializer(items, many=True).data)


class MenuItemDetailView(PublicCatalogueView):
    @extend_schema(summary="One menu item", responses={200: MenuItemSerializer, **errors(404)})
    def get(self, request, slug):
        item = get_object_or_404(MenuItem.objects.public().with_relations(), slug=slug)
        return Response(MenuItemSerializer(item).data)


class CategoryListView(PublicCatalogueView):
    @extend_schema(summary="Menu categories", responses={200: CategorySerializer(many=True)})
    def get(self, request):
        return Response(CategorySerializer(Category.objects.filter(is_active=True), many=True).data)


class DrinkSectionListView(PublicCatalogueView):
    @extend_schema(summary="Sections of the drinks page", responses={200: DrinkSectionSerializer(many=True)})
    def get(self, request):
        return Response(DrinkSectionSerializer(DrinkSection.objects.all(), many=True).data)


class TagListView(PublicCatalogueView):
    @extend_schema(summary="Labels shown on dish cards, by key",
                   responses={200: {"type": "object", "additionalProperties": LOCALIZED_SCHEMA}})
    def get(self, request):
        return Response(tags_dict())


class OptionGroupListView(PublicCatalogueView):
    @extend_schema(summary="Customisation groups, by id (only available choices)",
                   responses={200: {"type": "object", "additionalProperties": {"$ref": "#/components/schemas/OptionGroup"}}})
    def get(self, request):
        return Response({group["id"]: group for group in OptionGroupSerializer(option_groups(), many=True).data})


# ───────── Portal (contract §9) ─────────

CAN_EDIT = require("menu:edit", "labels:edit", any_of=True)


def admin_items():
    return MenuItem.objects.with_relations().select_related("updated_by")


class AdminMenuItemListView(APIView):
    permission_classes = [CAN_EDIT]

    @extend_schema(
        summary="All items with their state (draft/published) and pending changes",
        parameters=[*ITEM_FILTERS, OpenApiParameter("deleted", bool, description="true = only deleted items")],
        responses={200: AdminMenuItemSerializer(many=True), **errors(401, 403)},
    )
    def get(self, request):
        items = filter_items(admin_items(), request.query_params)
        deleted = request.query_params.get("deleted") == "true"
        items = items.filter(deleted_at__isnull=not deleted)
        return Response(AdminMenuItemSerializer(items, many=True).data)

    @extend_schema(summary="Create an item (saved as a draft)", request=MenuItemInputSerializer,
                   responses={201: AdminMenuItemSerializer, **errors(401, 403, 422)})
    def post(self, request):
        serializer = MenuItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.create_item(request.user, dict(serializer.validated_data))
        return Response(AdminMenuItemSerializer(item).data, status=status.HTTP_201_CREATED)


class AdminMenuItemDetailView(APIView):
    permission_classes = [CAN_EDIT]

    def get_item(self, slug):
        return get_object_or_404(admin_items(), slug=slug)

    @extend_schema(summary="One item (portal)", responses={200: AdminMenuItemSerializer, **errors(401, 403, 404)})
    def get(self, request, slug):
        return Response(AdminMenuItemSerializer(self.get_item(slug)).data)

    @extend_schema(
        summary="Edit an item",
        description="A published item keeps its live version: the changes are saved as its draft until "
        "POST …/publish. An item never published is edited directly (it is still a draft).",
        request=MenuItemInputSerializer,
        responses={200: AdminMenuItemSerializer, **errors(401, 403, 404, 422)},
    )
    def patch(self, request, slug):
        item = self.get_item(slug)
        serializer = MenuItemInputSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_item(request.user, item, dict(serializer.validated_data))
        return Response(AdminMenuItemSerializer(self.get_item(slug)).data)

    @extend_schema(summary="Remove an item from the menu (can be restored)", responses={204: None, **errors(401, 403, 404)})
    def delete(self, request, slug):
        services.delete_item(request.user, self.get_item(slug))
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMenuItemPublishView(APIView):
    permission_classes = [require("content:publish")]

    @extend_schema(summary="Publish an item: its pending changes go live together", request=None,
                   responses={200: AdminMenuItemSerializer, **errors(401, 403, 404, 409)})
    def post(self, request, slug):
        item = get_object_or_404(admin_items(), slug=slug)
        services.publish_item(request.user, item)
        return Response(AdminMenuItemSerializer(get_object_or_404(admin_items(), slug=slug)).data)


class AdminMenuItemDraftView(APIView):
    permission_classes = [CAN_EDIT]

    @extend_schema(summary="Discard the pending changes of a published item",
                   responses={200: AdminMenuItemSerializer, **errors(401, 403, 404)})
    def delete(self, request, slug):
        item = services.discard_draft(request.user, get_object_or_404(admin_items(), slug=slug))
        return Response(AdminMenuItemSerializer(item).data)


class AdminMenuItemRestoreView(APIView):
    permission_classes = [CAN_EDIT]

    @extend_schema(summary="Restore a removed item", request=None,
                   responses={200: AdminMenuItemSerializer, **errors(401, 403, 404)})
    def post(self, request, slug):
        item = services.restore_item(request.user, get_object_or_404(admin_items(), slug=slug))
        return Response(AdminMenuItemSerializer(item).data)
