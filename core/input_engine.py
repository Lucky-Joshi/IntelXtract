"""Input engine: classify, validate, and normalize scan targets (Phase 6).

A scan begins with a raw string: the user's clipboard, a shell argument, or
a GUI field.  This module turns that string into a classified, canonical
target plus a module-selection plan consumed by the scan planner.

Classification precedence (first match wins):

1. URL      — explicit scheme (``https://…``) or host-with-path/path
              (``example.com/x``, ``example.com:8080/y``)
2. EMAIL    — ``user@host`` where ``host`` is a hostname or IP literal
3. IP       — IPv4 or IPv6 (IPv6-with-port must use ``[addr]:port``)
4. HASH     — hex digest of 32 (md5), 40 (sha1), or 64 (sha256) characters
5. FILE     — path separators, drive letters, ``~``, dotfiles, or a known
              file extension (e.g. ``report.pdf``, ``/etc/passwd``)
6. DOMAIN   — valid hostname, at least one label after the first dot;
              internationalized names are accepted and normalized to
              punycode (``münchen.de`` → ``xn--mnchen-3ya.de``)
7. USERNAME — bare social-style handle (``alice``, ``alice_1``, ``@alice``)
8. UNKNOWN  — nothing above matched

Known trade-offs (documented):

- ``example.md`` classifies as FILE (Montenegro's TLD is eclipsed by the
  file-extension rule); domain extraction is unaffected for real domains.
- ``john.doe`` classifies as DOMAIN, not USERNAME, because it is a valid
  hostname; users must pass a bare handle (or quoted username) when the
  intent is a username.
- ``user@host`` (single-label host) is accepted as EMAIL; on public DNS it
  double-checks nothing, it is only a syntactic verdict.
- ``localhost:3000`` is USERNAME (no dot, no scheme); bind targets are
  outside the supported public-target surface for now.
- IPv6 with a port requires bracket notation: ``[2001:db8::1]:8443``.

Normalized targets carry a canonical ``value`` (punycoded host, lowercased
hash, defaulted URL scheme, compact IPv6), a ``type``, an optional ``port``,
and the ``host`` component when the target has one.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Collection
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from core.constants import ScanMode, TargetType
from core.exceptions import ValidationError

_MAX_LENGTH = 2048

# --- recognition patterns ----------------------------------------------------

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-]*://")
_HOST_PATH_RE = re.compile(r"^[^\s/]+(\.[^\s/]+)+(?::\d+)?[/?#]")
_HASH_RE = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,31}$")

# --- planned module collectors (Phases 8-15) ---------------------------------

_QUICK_MODULES: dict[TargetType, tuple[str, ...]] = {
    TargetType.DOMAIN: ("domain",),
    TargetType.IP: ("ip",),
    TargetType.URL: ("website",),
    TargetType.EMAIL: ("email",),
    TargetType.USERNAME: ("username",),
    TargetType.HASH: (),
    TargetType.FILE: ("metadata",),
    TargetType.UNKNOWN: (),
}

_DEEP_MODULES: dict[TargetType, tuple[str, ...]] = {
    TargetType.DOMAIN: ("domain", "website", "certificate", "news"),
    TargetType.IP: ("ip",),
    TargetType.URL: ("website", "domain", "certificate"),
    TargetType.EMAIL: ("email", "domain"),
    TargetType.USERNAME: ("username",),
    TargetType.HASH: (),
    TargetType.FILE: ("metadata",),
    TargetType.UNKNOWN: (),
}

_FILE_EXTENSIONS = frozenset(
    {
        "7z",
        "apk",
        "asc",
        "avi",
        "bak",
        "bat",
        "bmp",
        "bz2",
        "c",
        "cer",
        "cfg",
        "conf",
        "cpp",
        "crt",
        "csv",
        "db",
        "deb",
        "der",
        "dll",
        "dmg",
        "doc",
        "docx",
        "eot",
        "eps",
        "exe",
        "flac",
        "flv",
        "gif",
        "gz",
        "h",
        "htm",
        "html",
        "ico",
        "ini",
        "iso",
        "jar",
        "jpeg",
        "jpg",
        "js",
        "json",
        "key",
        "log",
        "md",
        "mkv",
        "mov",
        "mp3",
        "mp4",
        "mpeg",
        "mpg",
        "odf",
        "ods",
        "odt",
        "ogg",
        "opus",
        "otf",
        "pdf",
        "pem",
        "pfx",
        "php",
        "p12",
        "png",
        "ppt",
        "pptx",
        "ps",
        "pub",
        "py",
        "rar",
        "rb",
        "rpm",
        "rtf",
        "sh",
        "sig",
        "sql",
        "sqlite",
        "svg",
        "tar",
        "tex",
        "tgz",
        "ttf",
        "txt",
        "wav",
        "webm",
        "webp",
        "woff",
        "woff2",
        "xls",
        "xlsx",
        "xml",
        "xz",
        "yaml",
        "yml",
        "zip",
        "zst",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedTarget:
    """Canonical form of a scan target."""

    raw: str
    value: str
    type: TargetType
    port: int | None = None
    host: str | None = None


# --- helpers -----------------------------------------------------------------


def _split_port(raw: str) -> tuple[str, int | None]:
    """Split ``[v6]:port`` / ``host:port`` / bare forms into (host, port)."""
    s = raw.strip()
    if s.startswith("["):
        end = s.find("]")
        if end == -1:
            return s, None
        host = s[1:end]
        rest = s[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return (host, None) if not rest else (s, None)
    if s.count(":") == 1:
        host, _, maybe = s.rpartition(":")
        if maybe.isdigit():
            return host, int(maybe)
        return s, None
    return s, None


def _is_ip(raw: str) -> bool:
    host, _port = _split_port(raw)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _is_hostname(host: str, *, require_dot: bool = False) -> bool:
    """True when ``host`` is a valid hostname (optional single-label mode)."""
    if not host or len(host) > 253:
        return False
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    labels = ascii_host.rstrip(".").split(".")
    if require_dot and len(labels) == 1:
        return False
    for label in labels:
        if not (1 <= len(label) <= 63):
            return False
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label):
            return False
    return True


def _is_email_host(host: str) -> bool:
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
        return _is_ip(host)
    if _is_ip(host):
        return True
    plain, _port = _split_port(host)
    return bool(plain) and _is_hostname(plain, require_dot=False)


def _is_file(raw: str) -> bool:
    s = raw.strip()
    if s in {".", ".."} or len(s) > _MAX_LENGTH:
        return False
    if s.startswith(".") and " " not in s:
        return True  # dotfiles: `.env`, `.bashrc`, `.git`
    if re.match(r"^[A-Za-z]:[\\/]", s):
        return True  # Windows drive path
    if s.startswith(("~", "/", "./", "../")):
        return True
    if "\\" in s or "/" in s:
        return True
    if "." in s:
        extension = s.rsplit(".", 1)[1].lower()
        if extension in _FILE_EXTENSIONS:
            return True
    return False


# --- public API --------------------------------------------------------------


def classify(raw: str) -> TargetType:
    """Return the recognized :class:`TargetType` for ``raw`` (never raises).

    Whitespace is stripped for the verdict; empty/blank input classifies as
    :attr:`TargetType.UNKNOWN`.
    """
    s = raw.strip()
    if not s:
        return TargetType.UNKNOWN
    if _SCHEME_RE.match(s) or _HOST_PATH_RE.match(s):
        return TargetType.URL
    local, sep, host = s.rpartition("@")
    if sep and local and host and " " not in s and _is_email_host(host):
        return TargetType.EMAIL
    if _is_ip(s):
        return TargetType.IP
    if _HASH_RE.fullmatch(s.lower()):
        return TargetType.HASH
    if _is_file(s):
        return TargetType.FILE
    hostname, _port = _split_port(s)
    if hostname and _is_hostname(hostname.lower(), require_dot=True):
        return TargetType.DOMAIN
    handle = s[1:] if s.startswith("@") else s
    if _USERNAME_RE.fullmatch(handle):
        return TargetType.USERNAME
    return TargetType.UNKNOWN


def _normalize_domain(raw: str) -> NormalizedTarget:
    host, port = _split_port(raw)
    ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower()
    return NormalizedTarget(
        raw=raw,
        value=ascii_host,
        type=TargetType.DOMAIN,
        port=port,
        host=ascii_host,
    )


def _normalize_ip(raw: str) -> NormalizedTarget:
    host, port = _split_port(raw)
    canonical = ipaddress.ip_address(host).compressed
    return NormalizedTarget(
        raw=raw,
        value=canonical,
        type=TargetType.IP,
        port=port,
        host=canonical,
    )


def _normalize_url(raw: str) -> NormalizedTarget:
    candidate = raw.strip()
    if not _SCHEME_RE.match(candidate):
        candidate = "https://" + candidate
    parsed = urlsplit(candidate)
    netloc = parsed.netloc
    host = parsed.hostname or ""
    port = parsed.port
    ascii_host = host
    if host:
        try:
            ascii_host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            ascii_host = host.lower()
        prefix = ""
        if "@" in netloc:
            prefix = netloc.rsplit("@", 1)[0] + "@"
        suffix = f":{port}" if port is not None else ""
        netloc = prefix + ascii_host + suffix
    value = urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path, parsed.query, parsed.fragment)
    )
    return NormalizedTarget(
        raw=raw, value=value, type=TargetType.URL, port=port, host=ascii_host or None
    )


def _normalize_email(raw: str) -> NormalizedTarget:
    local, _, host = raw.rpartition("@")
    lower_host = host.lower()
    return NormalizedTarget(
        raw=raw,
        value=f"{local}@{lower_host}",
        type=TargetType.EMAIL,
        host=lower_host,
    )


def _normalize_username(raw: str) -> NormalizedTarget:
    handle = raw.strip()
    if handle.startswith("@"):
        handle = handle[1:]
    return NormalizedTarget(raw=raw, value=handle, type=TargetType.USERNAME)


def normalize(raw: str) -> NormalizedTarget:
    """Classify and normalize ``raw`` without raising for unknown targets.

    Prefer :func:`parse_target` when the caller wants actionable errors for
    empty/oversized input.
    """
    return parse_target(raw, strict=False)


def parse_target(raw: str, *, strict: bool = False) -> NormalizedTarget:
    """Validate, classify, and normalize a scan target.

    :raises ValidationError: for empty/blank input or (when ``strict=True``)
        inputs that classify as :attr:`TargetType.UNKNOWN`.
    """
    if not isinstance(raw, str):
        raise ValidationError("target must be a string")
    s = raw.strip()
    if not s:
        raise ValidationError("target must not be empty")
    if len(s) > _MAX_LENGTH:
        raise ValidationError(f"target exceeds {_MAX_LENGTH} characters")

    target_type = classify(s)
    if target_type is TargetType.UNKNOWN and strict:
        raise ValidationError(
            "target could not be recognized as a supported type "
            "(domain, ip, url, email, username, hash, file)"
        )

    if target_type is TargetType.URL:
        return _normalize_url(s)
    if target_type is TargetType.EMAIL:
        return _normalize_email(s)
    if target_type is TargetType.IP:
        return _normalize_ip(s)
    if target_type is TargetType.HASH:
        return NormalizedTarget(raw=s, value=s.lower(), type=target_type)
    if target_type is TargetType.DOMAIN:
        return _normalize_domain(s)
    if target_type is TargetType.USERNAME:
        return _normalize_username(s)
    return NormalizedTarget(raw=s, value=s, type=target_type)


def select_modules(
    target_type: TargetType,
    mode: ScanMode | str,
    available: Collection[str] | None = None,
) -> list[str]:
    """Return the module names eligible for ``target_type`` under ``mode``.

    ``custom`` reuses the deep profile (users then override with explicit
    names in the planner).  When ``available`` is provided the result is the
    intersection with it, sorted; an empty profile yields an empty list.
    """
    profiles = {
        ScanMode.DEEP: _DEEP_MODULES,
        ScanMode.CUSTOM: _DEEP_MODULES,
        ScanMode.QUICK: _QUICK_MODULES,
    }
    chosen = profiles[ScanMode(mode)].get(target_type, ())
    candidates = set(chosen)
    if available is not None:
        candidates = candidates.intersection(available)
    return sorted(candidates)
