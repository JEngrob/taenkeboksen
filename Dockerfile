FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main", "--stage", "all", "--out-json", "reports/latest.json", "--out-html", "reports/site/index.html"]

