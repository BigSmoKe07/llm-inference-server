import pytest
from pydantic import ValidationError
from api.models import PredictRequest, PredictResponse, ResultResponse


def test_predict_request_valid():
    req = PredictRequest(text="I love this!")
    assert req.text == "I love this!"


def test_predict_request_empty_text_rejected():
    with pytest.raises(ValidationError):
        PredictRequest(text="")


def test_predict_request_too_long_rejected():
    with pytest.raises(ValidationError):
        PredictRequest(text="x" * 2049)


def test_predict_response_has_job_id_and_status():
    resp = PredictResponse(job_id="abc-123")
    assert resp.status == "queued"


def test_result_response_complete():
    resp = ResultResponse(job_id="abc", status="complete", label="POSITIVE", score=0.98)
    assert resp.label == "POSITIVE"
    assert resp.score == pytest.approx(0.98)


def test_result_response_pending_has_no_label():
    resp = ResultResponse(job_id="abc", status="queued")
    assert resp.label is None
    assert resp.score is None
