FROM python:3.10-slim
WORKDIR /app

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install Python Libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run App
COPY . .
EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]
