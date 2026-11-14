FROM denoland/deno:bin-2.9.7 AS deno

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-vazirmatn \
      fonts-montserrat \
      fonts-noto-core \
      libgl1 libglib2.0-0 \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app
COPY --from=deno /deno /usr/local/bin/deno
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Exercise the real decoder without downloading or loading a Whisper model.
RUN python -c "import io, wave; from faster_whisper.audio import decode_audio; f = io.BytesIO(); w = wave.open(f, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(bytes(3200)); w.close(); f.seek(0); assert len(decode_audio(f)) == 1600"
COPY app ./app
COPY features ./features
COPY assets/fonts/README.md /app/assets/fonts/README.md

# Encoding -1 enables libass whole-event text layout for bidi/shaping across
# per-word override tags; reject older libass builds without that extension.
RUN mkdir -p /app/assets/fonts \
    && cp "$(fc-match -f '%{file}' 'Vazirmatn:style=Bold')" /app/assets/fonts/Vazirmatn-Bold.ttf \
    && cp "$(fc-match -f '%{file}' 'Montserrat:style=ExtraBold')" /app/assets/fonts/Montserrat-ExtraBold.ttf \
    && cp "$(fc-match -f '%{file}' 'Noto Sans Arabic:style=Bold')" /app/assets/fonts/NotoSansArabic-Bold.ttf \
    && cp "$(fc-match -f '%{file}' 'Noto Naskh Arabic:style=Bold')" /app/assets/fonts/NotoNaskhArabic-Bold.ttf \
    && cp "$(fc-match -f '%{file}' 'Noto Sans:style=Bold')" /app/assets/fonts/NotoSans-Bold.ttf \
    && cp "$(fc-match -f '%{file}' 'Noto Serif:style=Bold')" /app/assets/fonts/NotoSerif-Bold.ttf \
    && cp /usr/share/doc/fonts-vazirmatn/copyright /app/assets/fonts/Vazirmatn-COPYRIGHT \
    && cp /usr/share/doc/fonts-montserrat/copyright /app/assets/fonts/Montserrat-COPYRIGHT \
    && cp /usr/share/doc/fonts-noto-core/copyright /app/assets/fonts/Noto-FONTS-COPYRIGHT \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libass9)" ge "0.16.0" \
    && ffmpeg -hide_banner -filters 2>/dev/null | grep -qE '[[:space:]]ass[[:space:]]' \
    && ldd "$(ldconfig -p | awk '/libass\.so\.9/{print $NF; exit}')" | grep -q libharfbuzz

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

VOLUME ["/data"]
CMD ["python", "-m", "app.bot"]
