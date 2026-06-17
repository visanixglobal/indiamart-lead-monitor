FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY main.py .
COPY refresh_cookie.py .
COPY test_connection.py .

# Create persistent directories
RUN mkdir -p logs data

EXPOSE 8000

CMD ["python", "main.py"]
