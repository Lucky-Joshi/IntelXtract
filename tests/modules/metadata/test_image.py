"""Image EXIF extraction tests (Phase 14, S14.2/S14.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.metadata.image import ImageMetadataError, extract_image

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


def test_extracts_expected_exif_fields() -> None:
    record = extract_image(FIXTURE_DIR / "sample.jpg")

    assert record["format"] == "jpeg"
    assert record["width"] == 64
    assert record["height"] == 48
    assert record["camera_make"] == "Canon"
    assert record["camera_model"] == "Canon EOS Z"
    assert record["software"] == "IntelXtract 1.0"
    assert record["datetime"] == "2024:01:02 12:00:01"
    assert record["datetime_original"] == "2024:01:02 11:59:59"
    assert record["lens_model"] == "RF 24-105mm"


def test_gps_coordinates_converted_to_decimal() -> None:
    record = extract_image(FIXTURE_DIR / "sample.jpg")

    gps = record["gps"]
    assert gps["latitude"] == pytest.approx(2.559167)
    assert gps["longitude"] == pytest.approx(-1.018056)
    assert gps["lat_ref"] == "N"
    assert gps["lon_ref"] == "W"


def test_malformed_image_raises() -> None:
    with pytest.raises(ImageMetadataError):
        extract_image(FIXTURE_DIR / "malformed.jpg")


def test_missing_image_raises() -> None:
    with pytest.raises(ImageMetadataError):
        extract_image(FIXTURE_DIR / "does-not-exist.jpg")
