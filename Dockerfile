FROM denoland/deno:bin-2.9.7 AS deno

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-vazirmatn \
      fonts-montserrat \
      libgl1 libglib2.0-0 \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app
COPY --from=deno /deno /usr/local/bin/deno
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY features ./features

RUN mkdir -p /app/assets/fonts \
    && cp "$(fc-match -f '%{file}' 'Vazirmatn:style=Bold')" /app/assets/fonts/Vazirmatn-Bold.ttf \
    && cp "$(fc-match -f '%{file}' 'Montserrat:style=ExtraBold')" /app/assets/fonts/Montserrat-ExtraBold.ttf \
    && ffmpeg -hide_banner -filters 2>/dev/null | grep -qE '[[:space:]]ass[[:space:]]' \
    && ldd "$(ldconfig -p | awk '/libass\.so\.9/{print $NF; exit}')" | grep -q libharfbuzz

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

VOLUME ["/data"]
CMD ["python", "-m", "app.bot"]
