FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD gunicorn web_ui:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread --timeout 120 --keep-alive 60
