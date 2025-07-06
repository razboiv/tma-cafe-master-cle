FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "backend.app.main:app", "--bind", "0.0.0.0:5000"]
