"""Inspect effective routes on both flattened and deferred FastAPI routers."""
from fastapi.routing import APIRoute


def api_routes(app):
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        yield from (route for route in app.routes if isinstance(route, APIRoute))
    else:
        # Public RouteContext preserves include prefixes and inherited guards.
        yield from (context for context in iter_route_contexts(app.routes) if isinstance(context.route, APIRoute))
