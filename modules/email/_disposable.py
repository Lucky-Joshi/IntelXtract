"""Bundled disposable-address blocklist (private module).

The list deliberately covers only well-known anonymous/disposable mail
providers; operators extend it per deployment via ``email.disposable_extra``.
"""

from __future__ import annotations

BUNDLED_DISPOSABLE_DOMAINS: frozenset[str] = frozenset(
    {
        "10minutemail.com",
        "dispostable.com",
        "dropmail.me",
        "emailondeck.com",
        "getnada.com",
        "guerrillamail.com",
        "guerrillamailaffe.com",
        "maildrop.cc",
        "mailinator.com",
        "mailnesia.com",
        "mailsac.com",
        "mintemail.com",
        "moakt.com",
        "shut.name",
        "simplelogin.io",
        "spambox.us",
        "spam4.me",
        "temp-mail.org",
        "tempmail.com",
        "tempmailo.com",
        "throwawaymail.com",
        "trashmail.com",
        "yopmail.com",
    }
)
