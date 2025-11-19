import random
import time

from locust import HttpUser, between, task

TEXTS = [
    "I absolutely love this product, it changed my life!",
    "Terrible experience, would not recommend to anyone.",
    "It was okay, nothing special about it.",
    "Best purchase I have ever made, outstanding quality.",
    "Very disappointed with the quality and service.",
    "Exceeded all my expectations, truly remarkable.",
    "Complete waste of money, broke after one day.",
    "Decent product for the price, does the job.",
]


class InferenceUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.api_key = "REPLACE_WITH_YOUR_API_KEY"
        self.headers = {"X-API-Key": self.api_key}

    @task
    def predict_and_poll(self):
        # Submit job
        submit_response = self.client.post(
            "/predict",
            json={"text": random.choice(TEXTS)},
            headers=self.headers,
            name="POST /predict",
        )
        if submit_response.status_code != 200:
            return

        job_id = submit_response.json()["job_id"]

        # Poll until complete or timeout (max 10 attempts × 200ms = 2s)
        for attempt in range(10):
            time.sleep(0.2)
            result_response = self.client.get(
                f"/result/{job_id}",
                headers=self.headers,
                name="GET /result/{job_id}",
            )
            if result_response.status_code == 200:
                if result_response.json().get("status") in ("complete", "failed"):
                    break
