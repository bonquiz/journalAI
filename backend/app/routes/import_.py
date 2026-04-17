"""Import-Route: POST /api/import (multipart, dry_run + mode)."""
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.db import SessionLocal
from app.security.rate_limit import limiter
from app.services.embedding_jobs import request_backfill
from app.services.import_ import (
    ImportError as AppImportError,
    VALID_MODES,
    parse_export_zip,
    run_import,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/import")


@router.post("")
@limiter.limit("5/minute")
async def import_zip(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("skip"),
    dry_run: str = Form("false"),
) -> dict:
    if mode not in VALID_MODES:
        raise HTTPException(400, f"invalid mode: {mode}")
    is_dry = dry_run.lower() == "true"

    try:
        blob = await file.read()
        payload = parse_export_zip(blob)
    except AppImportError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.warning("import parse failed: %s", exc)
        raise HTTPException(400, "Import fehlgeschlagen — ZIP prüfen") from exc

    with SessionLocal() as db:
        try:
            result = run_import(db, payload, mode=mode, dry_run=is_dry)
        except AppImportError as exc:
            raise HTTPException(400, str(exc)) from exc

    if not is_dry and mode == "overwrite":
        request_backfill()

    return result
