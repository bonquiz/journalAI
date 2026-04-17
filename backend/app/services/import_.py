"""Import-Service: Parse, Plan, Apply für Export-ZIPs."""
import io
import json
import zipfile
from typing import Any

SUPPORTED_VERSIONS = {"1"}


class ImportError(Exception):
    """Geworfen bei Format-/Validierungs-Fehlern. Route-Layer mappt auf HTTP 400."""


def parse_export_zip(blob: bytes) -> dict[str, Any]:
    """Validiert und parst ein Export-ZIP. Wirft ImportError bei Fehlern."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob), "r")
    except zipfile.BadZipFile as exc:
        raise ImportError("ungültiges ZIP") from exc

    with zf:
        names = set(zf.namelist())
        if names != {"entries.json"}:
            if "entries.json" not in names:
                raise ImportError("entries.json fehlt im ZIP")
            raise ImportError("ZIP muss genau entries.json enthalten")
        try:
            raw = zf.read("entries.json").decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImportError(f"entries.json ist kein gültiges JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ImportError("entries.json muss ein Objekt sein")

    version = payload.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ImportError(f"unbekannte version: {version!r}")

    if not isinstance(payload.get("entries"), list):
        raise ImportError("entries muss ein Array sein")
    if not isinstance(payload.get("tags", []), list):
        raise ImportError("tags muss ein Array sein")

    return payload
