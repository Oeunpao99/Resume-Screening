FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (include poppler & tesseract for OCR fallback)
RUN apt-get update && apt-get install -y \
    gcc \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (repo root)
COPY . .

# Create necessary directories
RUN mkdir -p /app/data/uploaded_resumes /app/logs

# Expose port (Render will set PORT at runtime)
EXPOSE 8000

# Command: use PORT env var if provided. Render will set $PORT.
# Use sh -c so the shell expands the environment variable.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]