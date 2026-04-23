FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline.py .
COPY markov_transition.py .
COPY markov_analysis.py .
COPY merchant_scoring.py .
COPY upload_markov_analysis.py .
COPY scoring_query.sql .
COPY transition_query.sql .
COPY markov_analysis.csv .

CMD ["python", "pipeline.py"]