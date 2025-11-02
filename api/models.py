from pydantic import BaseModel, Field
from typing import Literal, Optional


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2048)


class PredictResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class ResultResponse(BaseModel):
    job_id: str
    status: Literal["queued", "complete", "failed"]
    label: Optional[str] = None
    score: Optional[float] = None
