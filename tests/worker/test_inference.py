# tests/worker/test_inference.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_classifier():
    """Returns a SentimentClassifier with a mocked HuggingFace pipeline."""
    mock_pipeline_instance = MagicMock(return_value=[{"label": "POSITIVE", "score": 0.98}])
    mock_pipeline_fn = MagicMock(return_value=mock_pipeline_instance)
    with patch("worker.inference.pipeline", mock_pipeline_fn):
        from worker.inference import SentimentClassifier
        classifier = SentimentClassifier()
    yield classifier


def test_predict_returns_label_and_score(mock_classifier):
    result = mock_classifier.predict("I love this!")
    assert result["label"] == "POSITIVE"
    assert result["score"] == pytest.approx(0.98)


def test_predict_negative_sentiment(mock_classifier):
    mock_classifier._pipeline.return_value = [{"label": "NEGATIVE", "score": 0.91}]
    result = mock_classifier.predict("This is terrible.")
    assert result["label"] == "NEGATIVE"
    assert result["score"] == pytest.approx(0.91)


def test_predict_truncates_text_to_512_chars(mock_classifier):
    long_text = "a" * 1000
    mock_classifier.predict(long_text)
    call_arg = mock_classifier._pipeline.call_args[0][0]
    assert len(call_arg) <= 512


def test_predict_passes_text_unchanged_when_short(mock_classifier):
    short_text = "Great product!"
    mock_classifier.predict(short_text)
    call_arg = mock_classifier._pipeline.call_args[0][0]
    assert call_arg == short_text
