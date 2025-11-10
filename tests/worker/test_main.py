# tests/worker/test_main.py
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_sqs_message():
    return {
        "Body": json.dumps({
            "job_id": "job-abc",
            "text": "Great product!",
            "submitted_at": "2026-04-04T10:00:00+00:00",
        }),
        "ReceiptHandle": "receipt-handle-123",
    }


def test_process_message_calls_inference_and_writes_result(mock_sqs_message):
    mock_classifier = MagicMock()
    mock_classifier.predict.return_value = {"label": "POSITIVE", "score": 0.97}

    with patch("worker.main.update_job_complete") as mock_complete, \
         patch("worker.main.update_job_failed") as mock_failed, \
         patch("worker.main.inference_requests_total") as mock_counter, \
         patch("worker.main.inference_latency_seconds") as mock_hist:

        from worker.main import process_message
        process_message(mock_classifier, mock_sqs_message)

    mock_classifier.predict.assert_called_once_with("Great product!")
    mock_complete.assert_called_once_with("job-abc", "POSITIVE", 0.97)
    mock_failed.assert_not_called()
    mock_counter.labels.assert_called_with(status="success")


def test_process_message_marks_failed_on_exception(mock_sqs_message):
    mock_classifier = MagicMock()
    mock_classifier.predict.side_effect = RuntimeError("model error")

    with patch("worker.main.update_job_complete") as mock_complete, \
         patch("worker.main.update_job_failed") as mock_failed, \
         patch("worker.main.inference_requests_total"):

        from worker.main import process_message
        with pytest.raises(RuntimeError):
            process_message(mock_classifier, mock_sqs_message)

    mock_complete.assert_not_called()
    mock_failed.assert_called_once_with("job-abc")
