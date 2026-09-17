from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .service import DefectTriageService


class DefectCreateRequest(BaseModel):
    title: str = Field(min_length=3)
    description: str = Field(min_length=5)
    component: str
    environment: str = "Production"
    severity: Literal["Critical", "High", "Medium", "Low"]
    tags: list[str] = Field(default_factory=list)
    reminder_profile: Literal["Demo", "Standard"] = "Standard"
    similarity_provider: Literal["local", "openai"] = "local"
    model: str = "gpt-4o-mini"


class StatusUpdateRequest(BaseModel):
    status: str


app = FastAPI(
    title="Defect Triage Assistant API",
    version="0.1.0",
    description="REST facade over the hackathon defect-triage service.",
)
app.state.service = DefectTriageService()


def _service() -> DefectTriageService:
    return app.state.service


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/defects")
def list_defects() -> list[dict[str, Any]]:
    return _service().list_defects()


@app.get("/api/defects/{defect_id}")
def get_defect(defect_id: int) -> dict[str, Any]:
    detail = _service().get_defect_detail(defect_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Defect not found")
    return detail


@app.post("/api/defects", status_code=201)
def create_defect(
    request: DefectCreateRequest,
    x_openai_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        defect_id = _service().create_defect(
            request.model_dump(exclude={"reminder_profile", "similarity_provider", "model"}),
            reminder_profile=request.reminder_profile,
            similarity_provider=request.similarity_provider,
            api_key=x_openai_api_key or os.getenv("OPENAI_API_KEY", ""),
            model=request.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return get_defect(defect_id)


@app.patch("/api/defects/{defect_id}/status")
def update_status(defect_id: int, request: StatusUpdateRequest) -> dict[str, Any]:
    try:
        _service().change_status(defect_id, request.status)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return get_defect(defect_id)
