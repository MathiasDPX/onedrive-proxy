FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir waitress

COPY . .

EXPOSE 80

CMD ["waitress-serve", "--host=0.0.0.0", "--port=80", "main:app"]