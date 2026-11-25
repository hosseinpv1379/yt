#!/bin/sh
# Set up an isolated Python runtime and start the local web service.
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
TOOLS="$ROOT/.localweb-tools"
RUNTIME="$ROOT/.localweb-python"
ENVIRONMENT="$ROOT/.venv-localweb"
export UV_PYTHON_INSTALL_DIR="$RUNTIME"
export UV_CACHE_DIR="$ROOT/.localweb-cache"
export UV_NO_MODIFY_PATH=1

if [ ! -x "$TOOLS/bin/uv" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        printf '%s\n' 'Python 3 برای نصب اولیه پیدا نشد.' >&2
        exit 1
    fi
    printf '%s\n' 'در حال آماده‌سازی ابزار نصب محلی…'
    python3 -m venv "$TOOLS"
    "$TOOLS/bin/python" -m pip install 'uv==0.13.9'
fi
if [ ! -f "$ENVIRONMENT/.setup-complete" ]; then
    printf '%s\n' 'در حال آماده‌سازی Python 3.12 و وابستگی‌ها؛ اجرای اول ممکن است طول بکشد…'
    "$TOOLS/bin/uv" python install 3.12 --no-bin
    "$TOOLS/bin/uv" venv --python 3.12 "$ENVIRONMENT"
    "$TOOLS/bin/uv" pip install --python "$ENVIRONMENT/bin/python" -r localweb/requirements.txt
    touch "$ENVIRONMENT/.setup-complete"
fi
printf '%s\n' 'برنامه در حال اجراست؛ برای توقف Ctrl+C را بزنید.'
exec "$ENVIRONMENT/bin/python" -m localweb "$@"
