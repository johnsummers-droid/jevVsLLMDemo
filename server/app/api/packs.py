"""GET /api/packs/{id}: a scenario pack's summary (T23): ticket count, categories for the practice
pack only, and the scoring targets the run UI colours its metrics against. Never ticket text."""

from fastapi import APIRouter, HTTPException

from app.models import PackSummary
from app.simulation.loader import PACK_IDS, pack_summary

router = APIRouter(prefix="/api/packs", tags=["packs"])


@router.get("/{pack_id}")
def get_pack(pack_id: str) -> PackSummary:
    if pack_id not in PACK_IDS:
        raise HTTPException(status_code=404, detail="no such pack")
    return pack_summary(pack_id)
