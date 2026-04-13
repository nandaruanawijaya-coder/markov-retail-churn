FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY merchant_scoring.py .
COPY scoring_query.sql .
COPY markov_analysis.csv .

CMD ["python", "merchant_scoring.py"]