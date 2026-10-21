FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 BEHIND_PROXY=true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/instance
EXPOSE 8000
# --preload: set up the database once, before workers start
CMD ["gunicorn", "--preload", "-w", "2", "-b", "0.0.0.0:8000", "--access-logfile", "-", "app:app"]
