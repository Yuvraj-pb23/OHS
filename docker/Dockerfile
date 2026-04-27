FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn","OHS.wsgi:application","--bind","0.0.0.0:8000","--certfile","/app/certs/localhost+1.pem","--keyfile","/app/certs/localhost+1-key.pem","--timeout","120"]