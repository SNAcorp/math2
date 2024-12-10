FROM python:3.12-slim

# Установите зависимости для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ./app .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--reload"]