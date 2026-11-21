"""Downloadable city report (PDF or print-ready HTML)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response

from core.reports import build_html, build_pdf, report_filename

from ..deps import valid_city, valid_persona
from .city import overview, weather

router = APIRouter(prefix="/api/cities/{city}", tags=["report"])


@router.get(
    "/report",
    responses={200: {"content": {"application/pdf": {}, "text/html": {}},
                     "description": "Consolidated report for the city and persona"}},
)
def report(
    city: str = Depends(valid_city),
    persona: str = Depends(valid_persona),
    format: Literal["pdf", "html"] = Query("pdf"),
    download: bool = Query(True, description="Send as attachment (false = open inline)"),
) -> Response:
    ov = overview(city, persona)
    wx = weather(city, persona)
    disposition = "attachment" if download else "inline"
    if format == "html":
        name = report_filename(city, persona, "html")
        return HTMLResponse(build_html(ov, wx),
                            headers={"Content-Disposition": f'{disposition}; filename="{name}"'})
    name = report_filename(city, persona, "pdf")
    return Response(build_pdf(ov, wx), media_type="application/pdf",
                    headers={"Content-Disposition": f'{disposition}; filename="{name}"'})
