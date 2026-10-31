FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "httpx>=0.27"

COPY loadgen.py .

RUN useradd --create-home app
USER app

CMD ["python", "loadgen.py"]
