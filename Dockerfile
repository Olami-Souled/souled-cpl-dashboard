FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
