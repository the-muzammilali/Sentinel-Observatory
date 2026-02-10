# Multi-stage build for Sentinel Observatory Backend
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Add local bin to PATH for builder to suppress warnings
ENV PATH=/root/.local/bin:$PATH

# Install Python dependencies

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Final stage
# ============================================================================
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 sentinel && \
    mkdir -p /app /app/data /app/logs && \
    chown -R sentinel:sentinel /app

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/sentinel/.local

# Copy application code
COPY --chown=sentinel:sentinel . .

# Switch to non-root user
USER sentinel

# Add local bin to PATH
ENV PATH=/home/sentinel/.local/bin:$PATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Run the application
CMD ["python", "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
