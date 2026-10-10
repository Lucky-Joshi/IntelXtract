"""Image EXIF extraction (Phase 14, S14.2) via ``Pillow``.

Reads only the EXIF header blocks (camera make/model, software, timestamps,
GPS) without decoding pixel payloads, and caps the decompression bomb size
so deeply hostile images fail fast instead of exhausting memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

# Decompression-bomb guard: refuse images advertising more pixels than this.
_MAX_IMAGE_PIXELS = 100_000_000

_EXIF_STRINGS: dict[int, str] = {
    0x010F: "camera_make",  # Make
    0x0110: "camera_model",  # Model
    0x0131: "software",  # Software
    0x0132: "datetime",  # DateTime
    0x9003: "datetime_original",  # DateTimeOriginal
    0x9004: "datetime_digitized",  # DateTimeDigitized
    0x013B: "artist",  # Artist
    0x010E: "image_description",  # ImageDescription
    0xA431: "camera_serial",  # CameraSerialNumber
    0xA434: "lens_model",  # LensModel
    0x8298: "copyright",  # Copyright
}


class ImageMetadataError(ValueError):
    """Raised when a file cannot be opened or has no readable EXIF."""


def _rational(value: Any) -> float:
    """Normalize a Pillow rational (Fraction, float, or ``(num, den)``) to float."""
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and not isinstance(value, (int, float))
    ):
        numerator, denominator = value
        try:
            if denominator == 0:
                return 0.0
            return float(numerator) / float(denominator)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(value)  # Fraction, IFDRational, ints, plain floats
    except (TypeError, ValueError):
        return 0.0


def _dms(value: Any) -> float:
    """Convert a DMS rational tuple to decimal degrees."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, tuple) and len(value) == 3:
        degrees, minutes, seconds = value
        return (
            _rational(degrees)
            + (_rational(minutes) / 60.0)
            + (_rational(seconds) / 3600.0)
        )
    if isinstance(value, tuple) and len(value) == 2:
        return _rational(value)
    return 0.0


def _gps_coordinates(gps: dict[int, Any]) -> dict[str, Any] | None:
    latitude = gps.get(2)  # GPSLatitude
    longitude = gps.get(4)  # GPSLongitude
    if latitude is None or longitude is None:
        return None
    lat_ref = str(gps.get(1) or "N")  # GPSLatitudeRef
    lon_ref = str(gps.get(3) or "E")  # GPSLongitudeRef
    lat = _dms(latitude)
    lon = _dms(longitude)
    return {
        "latitude": round(lat, 6) * (-1 if "S" in lat_ref.upper() else 1),
        "longitude": round(lon, 6) * (-1 if "W" in lon_ref.upper() else 1),
        "lat_ref": lat_ref.upper(),
        "lon_ref": lon_ref.upper(),
    }


def extract_image(path: str | Path) -> dict[str, Any]:
    """Return EXIF-backed properties, raising on unreadable files."""
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            record: dict[str, Any] = {
                "format": (image.format or "").lower(),
                "width": image.width,
                "height": image.height,
            }
            for tag_id, field in _EXIF_STRINGS.items():
                tag_value = exif.get(tag_id)
                if isinstance(tag_value, bytes):
                    tag_value = tag_value.decode("utf-8", errors="replace")
                value = str(tag_value).strip()
                if value:
                    record[field] = value
            if 0x8825 in exif:
                gps = exif.get_ifd(0x8825)
                coordinates = _gps_coordinates(gps)
                if coordinates is not None:
                    record["gps"] = coordinates
            return record
    except Image.DecompressionBombError as exc:
        raise ImageMetadataError(f"image too large: {exc}") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise ImageMetadataError(f"unreadable image: {exc}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


__all__ = ["ImageMetadataError", "extract_image"]
