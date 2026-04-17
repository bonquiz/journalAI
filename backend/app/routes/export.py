"""Export-Route: GET /api/export → ZIP-Download."""
from fastapi import APIRouter
from fastapi.responses import Response

from app.db import SessionLocal
from app.services.export import export_zip_bytes
from app.utc import utc_now

router = APIRouter(prefix="/api/export")


@router.get("")
async def export_zip() -> Response:
    with SessionLocal() as db:
        blob = export_zip_bytes(db)
    date_tag = utc_now().date().isoformat()
    filename = f"journalai-export-{date_tag}.zip"
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
