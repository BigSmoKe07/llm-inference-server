import json
from unittest.mock import patch, MagicMock


def test_enqueue_job_sends_correct_message():
    mock_sqs = MagicMock()
    with patch("api.queue.boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_sqs
        from api.queue import enqueue_job
        enqueue_job("job-1", "I love this!", "2026-04-04T10:00:00+00:00")

    mock_sqs.send_message.assert_called_once()
    call_kwargs = mock_sqs.send_message.call_args[1]
    body = json.loads(call_kwargs["MessageBody"])
    assert body["job_id"] == "job-1"
    assert body["text"] == "I love this!"
    assert body["submitted_at"] == "2026-04-04T10:00:00+00:00"
