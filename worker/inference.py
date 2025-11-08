import time

from prometheus_client import Gauge
from transformers import pipeline

model_load_seconds = Gauge(
    "inference_model_load_seconds",
    "Seconds taken to load the model at startup",
)


class SentimentClassifier:
    def __init__(self) -> None:
        start = time.perf_counter()
        self._pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
        )
        model_load_seconds.set(time.perf_counter() - start)

    def predict(self, text: str) -> dict:
        result = self._pipeline(text[:512])[0]
        return {"label": result["label"], "score": float(result["score"])}
