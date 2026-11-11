FROM python:3.12-alpine
RUN apk add --no-cache tzdata && mkdir -p /data && chown nobody /data
COPY relay.py /app/relay.py
USER nobody
VOLUME /data
CMD ["python", "-u", "/app/relay.py"]
