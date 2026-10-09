"""Phase 10 website collectors: headers, tech, favicon, robots, http_methods."""

from __future__ import annotations

from modules.website.favicon import FaviconModule
from modules.website.headers import HeadersModule
from modules.website.http_methods import HttpMethodsModule
from modules.website.robots import RobotsModule
from modules.website.tech_stack import TechStackModule

__all__ = [
    "FaviconModule",
    "HeadersModule",
    "HttpMethodsModule",
    "RobotsModule",
    "TechStackModule",
]
