FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake model weights into image to avoid download on ECS task startup.
# distilbert-base-uncased-finetuned-sst-2-english is ~260MB.
RUN python -c "\
from transformers import pipeline; \
pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')"

COPY worker/ ./worker/

EXPOSE 9090

CMD ["python", "-m", "worker.main"]
