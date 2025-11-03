from pydantic import BaseModel, Field
from typing import Literal, Optional


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2048)


class PredictResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class ResultResponse(BaseModel):
    """
    Result for a prediction job.

    When status is 'queued' or 'failed': label and score are None.
    When status is 'complete': label and score are populated.
    """

    job_id: str
    status: Literal["queued", "complete", "failed"]
    label: Optional[str] = Field(None, min_length=1)
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
