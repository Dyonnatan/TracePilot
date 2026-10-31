FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home app
USER app

EXPOSE 8001
# Sem access log: as chamadas de /internal/* do chaos-control não devem
# deixar rastro em nenhum sinal do serviço.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
