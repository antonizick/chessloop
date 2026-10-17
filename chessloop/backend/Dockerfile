# Python 3.12 gets security fixes until 2028-10 (https://devguide.python.org/versions/)
FROM python:3.12.15-slim-trixie

WORKDIR /app

# Every dependency ships a binary wheel, so no compiler is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

EXPOSE 8000

# start.py checks JWT_SECRET, then execs uvicorn (PID 1, gets signals directly).
CMD ["python", "start.py"]
