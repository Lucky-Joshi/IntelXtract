"""Phase 12 collectors: username presence checks.

The only registered collector is :class:`UsernameModule` ("username");
``sites.json`` shipping the pattern list is a data file, not a module.
"""

from __future__ import annotations

from modules.username.collector import UsernameModule

__all__ = ["UsernameModule"]
