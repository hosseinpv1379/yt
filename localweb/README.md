# YT Local

This is a local-only web interface for the existing media processing code. It listens exclusively on `127.0.0.1`, opens a browser, and does not require Telegram or PostgreSQL. This is a development version, not yet a self-contained installer.

On macOS or Linux, start from the project root:

```sh
./run-local.sh
```

The first run downloads Python 3.12 and dependencies into ignored folders inside the project; it needs an existing `python3` with `venv` and an internet connection. Later runs reuse the environment. The application prints the local URL and opens it in the default browser. Stop it with Ctrl+C. API keys are kept in the system keyring, and output is saved to the configured folder. The model page downloads multilingual Whisper models for local captioning.

This version still requires system tools, fonts, and Spleeter for smart dubbing. It does not yet provide self-contained macOS/Windows builds, all model/dependency management, or full end-to-end validation. API and download features still require internet access. The web UI accepts local file paths; it does not yet include a native file picker.
