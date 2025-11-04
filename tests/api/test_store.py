import pytest
from unittest.mock import patch, MagicMock
import time


def test_put_job_writes_correct_item():
    mock_table = MagicMock()
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import put_job
        put_job("job-1", "hello world", "2026-04-04T10:00:00+00:00")

    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["job_id"] == "job-1"
    assert item["status"] == "queued"
    assert item["text"] == "hello world"
    assert "ttl" in item
    assert item["ttl"] > int(time.time())


def test_get_job_returns_item_when_found():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"job_id": "job-1", "status": "complete", "label": "POSITIVE", "score": "0.98"}
    }
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import get_job
        result = get_job("job-1")

    assert result["job_id"] == "job-1"
    assert result["status"] == "complete"


def test_get_job_returns_none_when_not_found():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import get_job
        result = get_job("missing-job")

    assert result is None
