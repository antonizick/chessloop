# Python 3.12 gets security fixes until 2028-10 (https://devguide.python.org/versions/)
FROM python:3.14.8-slim-trixie

WORKDIR /app

# Every dependency ships a binary wheel, so no compiler is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The API runs as an unprivileged user (uid 10001), not root. A new data volume
# takes /data's owner from the image; an older one, made when the API ran as
# root, is handed over by the data-owner service in docker-compose.prod.yml.
RUN groupadd --system --gid 10001 chessloop \
 && useradd --system --uid 10001 --gid chessloop --home-dir /app --no-create-home \
        --shell /usr/sbin/nologin chessloop \
 && mkdir -p /data && chown chessloop:chessloop /data

USER 10001:10001

EXPOSE 8000

# start.py checks JWT_SECRET, then execs uvicorn (PID 1, gets signals directly).
CMD ["python", "start.py"]
