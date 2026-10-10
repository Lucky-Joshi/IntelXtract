"""Phase 11 S11.1: address syntax, structure, disposable blocklist."""

from __future__ import annotations

from modules.email._disposable import BUNDLED_DISPOSABLE_DOMAINS
from modules.email.validation import (
    classify,
    domain_of,
    is_disposable,
    local_part,
    normalize_email,
    syntax_valid,
)


def test_syntax_valid_addresses() -> None:
    assert syntax_valid("alice@example.com")
    assert syntax_valid("Alice+tag@sub.example.co.uk")
    assert syntax_valid("a.b_c@xn--80ak6aa92e.com")
    assert not syntax_valid("alice@localhost")
    assert not syntax_valid("alice example.com")
    assert not syntax_valid("alice@@example.com")
    assert not syntax_valid("@example.com")
    assert not syntax_valid("alice@")


def test_normalize_local_and_domain() -> None:
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"
    assert local_part(" Alice@Example.COM ") == "alice"
    assert domain_of(" Alice@Example.COM ") == "example.com"
    assert domain_of("not-an-email") is None
    assert local_part("not-an-email") is None


def test_disposable_classification() -> None:
    assert is_disposable("mailinator.com")
    assert is_disposable("Yopmail.com")
    assert not is_disposable("example.com")
    assert not is_disposable(None)
    # operator-supplied extras extend the bundled list
    assert is_disposable("corp-throwaway.example", ["corp-throwaway.example"])
    assert not is_disposable("example.com", ["  ", ""])


def test_bundled_blocklist_is_lowercase_and_unique() -> None:
    domains = list(BUNDLED_DISPOSABLE_DOMAINS)
    assert len(domains) == len(BUNDLED_DISPOSABLE_DOMAINS)
    assert all(d == d.lower() and "." in d for d in domains)


def test_classify_shape() -> None:
    good = classify("alice@example.com", [])
    assert good == {
        "syntax": True,
        "local": "alice",
        "domain": "example.com",
        "disposable": False,
    }
    bad = classify("alice@@example.com", [])
    assert bad["syntax"] is False
    assert bad["domain"] is None
    assert bad["disposable"] is False
