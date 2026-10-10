"""Phase 11 collectors: email address intelligence.

The registered collectors are :class:`EmailModule` (validation + mail-domain
DNS + Gravatar) and :class:`BreachModule` (HIBP, key-gated).  The remaining
modules in this package are plain helper/functions with no ``BaseModule``
subclasses, so discovery does not register them.
"""

from __future__ import annotations

from modules.email.breach import BreachModule
from modules.email.collector import EmailModule

__all__ = ["BreachModule", "EmailModule"]
