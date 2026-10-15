from core.routing import route

from . import views
from .views import ORDER_ID

urlpatterns = [
    route("orders", views.OrdersView.as_view(), "orders"),
    route(f"orders/{ORDER_ID}", views.StaffOrderDetailView.as_view(), "order"),
    route(f"orders/{ORDER_ID}/transition", views.OrderTransitionView.as_view(), "order-transition"),
    route(f"orders/{ORDER_ID}/payment", views.OrderPaymentView.as_view(), "order-payment"),
    route(f"orders/{ORDER_ID}/assign", views.OrderAssignView.as_view(), "order-assign"),
    route("me/orders", views.MyOrdersView.as_view(), "my-orders"),
    route(f"me/orders/{ORDER_ID}", views.MyOrderDetailView.as_view(), "my-order"),
]
