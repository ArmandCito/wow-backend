from django.urls import re_path


def route(pattern, view, name=None):
    """
    URL with an optional trailing slash: route("auth/sign-in", ...) matches /auth/sign-in and
    /auth/sign-in/. Path parameters use regex groups, e.g. r"orders/(?P<order_id>[\\w-]+)".
    """
    return re_path(rf"^{pattern}/?$", view, name=name)
