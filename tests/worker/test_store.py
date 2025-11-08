# tests/worker/test_store.py
from unittest.mock import patch, MagicMock


def test_update_job_complete_sets_correct_attributes():
    mock_table = MagicMock()
    with patch("worker.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from worker.store import update_job_complete
        update_job_complete("job-1", "POSITIVE", 0.9876)

    mock_table.update_item.assert_called_once()
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["Key"] == {"job_id": "job-1"}
    values = kwargs["ExpressionAttributeValues"]
    assert values[":s"] == "complete"
    assert values[":l"] == "POSITIVE"
    assert values[":sc"] == "0.9876"


def test_update_job_failed_sets_status_failed():
    mock_table = MagicMock()
    with patch("worker.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from worker.store import update_job_failed
        update_job_failed("job-1")

    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["Key"] == {"job_id": "job-1"}
    assert kwargs["ExpressionAttributeValues"][":s"] == "failed"
