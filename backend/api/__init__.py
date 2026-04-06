"""
Mapo REST API package.

Usage::

    from backend.api import register_routes
    register_routes(app)

where *app* is a Bottle WSGI application (typically the one from
botasaurus_server).
"""

from backend.api.routes import register_routes

__all__ = ["register_routes"]
