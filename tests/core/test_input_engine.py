"""Input engine tests: classification, normalization, validation (S6.4)."""

from __future__ import annotations

import pytest

from core.constants import ScanMode, TargetType
from core.exceptions import ValidationError
from core.input_engine import classify, normalize, parse_target, select_modules

CLASSIFY_CASES = [
    # --- URLs (scheme or host/path) ---
    ("https://example.com", TargetType.URL),
    ("http://example.com/path", TargetType.URL),
    ("ftp://1.2.3.4/pub", TargetType.URL),
    ("example.com/path", TargetType.URL),
    ("example.com?q=1", TargetType.URL),
    ("sub.example.com:8080/endpoint", TargetType.URL),
    # --- email (user@host) ---
    ("user@example.com", TargetType.EMAIL),
    ("first.last@mail.example.co.uk", TargetType.EMAIL),
    ("user@[1.2.3.4]", TargetType.EMAIL),
    ("user@1.2.3.4", TargetType.EMAIL),
    ("user@host", TargetType.EMAIL),
    # --- IP (v4/v6, optional port) ---
    ("1.2.3.4", TargetType.IP),
    ("255.255.255.255", TargetType.IP),
    ("1.2.3.4:8080", TargetType.IP),
    ("2001:db8::1", TargetType.IP),
    ("::1", TargetType.IP),
    ("[2001:db8::1]:443", TargetType.IP),
    ("2606:4700:4700::1111", TargetType.IP),
    # --- hash ---
    ("d41d8cd98f00b204e9800998ecf8427e", TargetType.HASH),
    ("DA39A3EE5E6B4B0D3255BFEF95601890AFD80709", TargetType.HASH),
    (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        TargetType.HASH,
    ),
    # --- file paths / dotfiles / known extensions ---
    ("/etc/passwd", TargetType.FILE),
    ("~/docs/report.pdf", TargetType.FILE),
    ("./archive.tar.gz", TargetType.FILE),
    ("C:\\Users\\someone\\photo.jpg", TargetType.FILE),
    ("report.pdf", TargetType.FILE),
    ("data.json", TargetType.FILE),
    ("notes.md", TargetType.FILE),
    ("script.sh", TargetType.FILE),
    (".env", TargetType.FILE),
    (".bashrc", TargetType.FILE),
    # --- domains (incl. IDN, ports, trailing dot) ---
    ("example.com", TargetType.DOMAIN),
    ("www.example.com", TargetType.DOMAIN),
    ("sub.example.co.uk", TargetType.DOMAIN),
    ("EXAMPLE.COM", TargetType.DOMAIN),
    ("münchen.de", TargetType.DOMAIN),
    ("example.com:8080", TargetType.DOMAIN),
    ("example.com.", TargetType.DOMAIN),
    ("xn--mnchen-3ya.de", TargetType.DOMAIN),
    ("123.example.com", TargetType.DOMAIN),
    # --- bare usernames ---
    ("alice", TargetType.USERNAME),
    ("alice_1", TargetType.USERNAME),
    ("alice-1", TargetType.USERNAME),
    ("@alice", TargetType.USERNAME),
    ("user123", TargetType.USERNAME),
    ("localhost", TargetType.USERNAME),
    # --- unknown ---
    ("", TargetType.UNKNOWN),
    ("   ", TargetType.UNKNOWN),
    ("???", TargetType.UNKNOWN),
    ("not a target", TargetType.UNKNOWN),
    ("a+b", TargetType.UNKNOWN),
]

NORMALIZE_CASES = [
    # (raw, type, value, port, host)
    ("https://example.com", TargetType.URL, "https://example.com", None, "example.com"),
    (
        "example.com/path",
        TargetType.URL,
        "https://example.com/path",
        None,
        "example.com",
    ),
    (
        "HTTPS://Example.COM/A",
        TargetType.URL,
        "https://example.com/A",
        None,
        "example.com",
    ),
    (
        "sub.example.com:8080/endpoint",
        TargetType.URL,
        "https://sub.example.com:8080/endpoint",
        8080,
        "sub.example.com",
    ),
    ("münchen.de", TargetType.DOMAIN, "xn--mnchen-3ya.de", None, "xn--mnchen-3ya.de"),
    ("EXAMPLE.COM.", TargetType.DOMAIN, "example.com", None, "example.com"),
    ("example.com:8443", TargetType.DOMAIN, "example.com", 8443, "example.com"),
    ("2001:0db8:0:0:0:0:0:1", TargetType.IP, "2001:db8::1", None, "2001:db8::1"),
    ("1.2.3.4:8080", TargetType.IP, "1.2.3.4", 8080, "1.2.3.4"),
    ("[2001:db8::1]:443", TargetType.IP, "2001:db8::1", 443, "2001:db8::1"),
    (
        "DA39A3EE5E6B4B0D3255BFEF95601890AFD80709",
        TargetType.HASH,
        "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        None,
        None,
    ),
    ("User@Example.COM", TargetType.EMAIL, "User@example.com", None, "example.com"),
    ("@alice", TargetType.USERNAME, "alice", None, None),
    ("/etc/passwd", TargetType.FILE, "/etc/passwd", None, None),
    ("  example.com  ", TargetType.DOMAIN, "example.com", None, "example.com"),
]

SELECT_CASES = [
    (TargetType.DOMAIN, ScanMode.QUICK, None, ["dns", "http"]),
    (
        TargetType.DOMAIN,
        ScanMode.DEEP,
        None,
        [
            "certificate",
            "dns",
            "http",
            "news",
            "ssl",
            "subdomain",
            "website",
            "whois",
        ],
    ),
    (TargetType.IP, ScanMode.QUICK, None, ["geo", "rdns"]),
    (TargetType.IP, ScanMode.DEEP, None, ["geo", "rdns", "reputation"]),
    (TargetType.URL, ScanMode.QUICK, None, ["website"]),
    (TargetType.HASH, ScanMode.QUICK, None, []),
    (TargetType.UNKNOWN, ScanMode.DEEP, None, []),
    (
        TargetType.DOMAIN,
        ScanMode.DEEP,
        {"website", "news"},
        ["news", "website"],
    ),
    (TargetType.DOMAIN, ScanMode.QUICK, {"domain", "ghost"}, []),
    (TargetType.DOMAIN, ScanMode.QUICK, set(), []),
    (
        TargetType.DOMAIN,
        ScanMode.CUSTOM,
        None,
        [
            "certificate",
            "dns",
            "http",
            "news",
            "ssl",
            "subdomain",
            "website",
            "whois",
        ],
    ),
]


@pytest.mark.parametrize("raw,expected", CLASSIFY_CASES)
def test_classify(raw: str, expected: TargetType) -> None:
    assert classify(raw) is expected


@pytest.mark.parametrize("raw,target_type,value,port,host", NORMALIZE_CASES)
def test_normalize(
    raw: str, target_type: TargetType, value: str, port: int | None, host: str | None
) -> None:
    target = normalize(raw)
    assert target.type is target_type
    assert target.value == value
    assert target.port == port
    assert target.host == host


@pytest.mark.parametrize("target_type,mode,available,expected", SELECT_CASES)
def test_select_modules(
    target_type: TargetType,
    mode: ScanMode,
    available: set[str] | None,
    expected: list[str],
) -> None:
    assert select_modules(target_type, mode, available) == expected


def test_parse_target_round_trip_is_immutable() -> None:
    target = parse_target("Example.COM.", strict=True)
    assert target.raw == "Example.COM."
    assert target.value == "example.com"
    assert target.type is TargetType.DOMAIN
    assert target.host == "example.com"


def test_parse_target_accepts_string_modes() -> None:
    assert select_modules(TargetType.IP, "deep") == ["geo", "rdns", "reputation"]


def test_parse_target_rejects_blank() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        parse_target("   ")


def test_parse_target_rejects_oversized() -> None:
    with pytest.raises(ValidationError, match="exceeds"):
        parse_target("x" * 3000)


def test_parse_target_non_string() -> None:
    with pytest.raises(ValidationError, match="must be a string"):
        parse_target(1234)  # type: ignore[arg-type]


def test_parse_target_strict_rejects_unknown() -> None:
    with pytest.raises(ValidationError, match="could not be recognized"):
        parse_target("???", strict=True)


def test_parse_target_lenient_returns_unknown() -> None:
    assert parse_target("???", strict=False).type is TargetType.UNKNOWN


def test_ip_classification_excludes_invalid_octets() -> None:
    assert classify("999.1.1.1") is TargetType.DOMAIN
    assert classify("1.2.3.4.5") is TargetType.DOMAIN


def test_ipv6_without_brackets_is_untouched() -> None:
    target = parse_target("2001:db8::1")
    assert target.type is TargetType.IP
    assert target.port is None


def test_username_with_dot_prefers_domain() -> None:
    assert classify("john.doe") is TargetType.DOMAIN


def test_select_modules_custom_reuses_deep_profile() -> None:
    assert select_modules(TargetType.URL, "custom") == [
        "certificate",
        "domain",
        "website",
    ]
