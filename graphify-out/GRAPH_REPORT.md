# Graph Report - yt  (2026-11-26)

## Corpus Check
- 56 files · ~52,400 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: (none) 10, .separator 1, .conf 1)

## Summary
- 822 nodes · 2267 edges · 41 communities (29 shown, 12 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 136 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f8cb3454`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- worker
- Database
- domain_manager.py
- downloads.py
- test_subtitles.py
- database.py
- openai_limits.py
- _synthesize_fitting_dub
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- test_model_settings.py
- Project agent guidance
- DatabaseIntegrationTests
- test_localweb_settings.py
- features/__init__.py
- app/pipeline.py
- video_captions/__init__.py
- process_video
- WalletTransaction
- test_database_integration.py
- fonts/README.md
- __main__.py
- pathlib
- image_generation.py
- run-local.sh
- BotState
- Path
- handlers.py
- admin_callback
- models.py
- test_conversation_progress.py
- server.py
- ModelSelection
- LocalService
- OpenRouterRateLimiter
- app.js
- OrderHistoryTests
- BotSetting
- SeparatorTests
- localweb/README.md
- tkinter

## God Nodes (most connected - your core abstractions)
1. `Database` - 75 edges
2. `BotState` - 63 edges
3. `_state()` - 48 edges
4. `main()` - 36 edges
5. `button()` - 36 edges
6. `process_video()` - 34 edges
7. `_edit_query_screen()` - 29 edges
8. `worker()` - 25 edges
9. `back_keyboard()` - 24 edges
10. `admin_callback()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `ConversationProgressTests` --uses--> `BotState`  [INFERRED]
  tests/test_conversation_progress.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `DownloadOrderTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `MinuteEstimateTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py

## Import Cycles
- None detected.

## Communities (41 total, 12 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.07
Nodes (109): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+101 more)

### Community 1 - "worker"
Cohesion: 0.18
Nodes (22): _automatic_backup_loop(), _finish_progress(), Job, _job_refund_note(), _load_admin_settings(), _notify_admin_cost(), post_init(), _progress_updater() (+14 more)

### Community 3 - "domain_manager.py"
Cohesion: 0.06
Nodes (35): create_database_backup(), Path, PostgreSQL backup creation for scheduled delivery to the configured admin., _bounded_int(), _env(), load_settings(), parse_admin_setting(), Startup credentials and defaults for settings managed by the Telegram admin… (+27 more)

### Community 4 - "downloads.py"
Cohesion: 0.06
Nodes (50): DownloadJob, _run_download_job(), edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), _best_media_url() (+42 more)

### Community 5 - "test_subtitles.py"
Cohesion: 0.10
Nodes (21): _audio_chunk_offsets(), Use the actual segment muxer boundaries, not nominal 8-minute offsets., _srt_time(), _transcribe(), _write_srt(), caption_cues(), _caption_parts(), _coverage() (+13 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, CardTransferRequest, ContentOrder, DownloadRecord, DownloadTask, ImageOrder, PaymentOrder, datetime (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.24
Nodes (10): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+2 more)

### Community 8 - "_synthesize_fitting_dub"
Cohesion: 0.13
Nodes (11): _dub_group_slot(), _fit_dub_speech(), _shorten_dub_text(), _synthesize_fitting_dub(), _translation_cost(), asyncio, AudioSegment, pydub (+3 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.14
Nodes (13): HTTPS و دامنهٔ دانلود, اجرا با Docker, اجرای محلی بدون Docker, بسته‌های دقیقه, بکاپ خودکار دیتابیس, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی, زیرنویس انیمیشنی ویدیوی ارسالی (+5 more)

### Community 10 - "test_model_settings.py"
Cohesion: 0.18
Nodes (5): CostDisplayTests, MemoryDB, MinuteEstimateTests, ModelSettingsTests, settings()

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "test_localweb_settings.py"
Cohesion: 0.31
Nodes (4): load_preferences(), pipeline_settings(), save_preferences(), LocalWebSettingsTests

### Community 15 - "app/pipeline.py"
Cohesion: 0.11
Nodes (22): cleanup(), generate(), get_available_qualities(), get_video_details(), get_video_details_with_title(), _isolate_ltr_runs(), OpenAICost, Probe a YouTube URL and return available heights, duration, and title. (+14 more)

### Community 17 - "process_video"
Cohesion: 0.17
Nodes (18): Settings, _check_cancel(), _configure_realtime_speech(), _create_dubbed_audio(), _create_openrouter_dubbed_audio(), _download(), _make_dub_groups(), _media_duration() (+10 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.25
Nodes (4): JobRecord, datetime, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 21 - "__main__.py"
Cohesion: 0.12
Nodes (15): argparse, http_client, json, Single-user local web interface., main(), make_server(), do_GET(), do_POST() (+7 more)

### Community 22 - "pathlib"
Cohesion: 0.13
Nodes (15): importlib_util, Single-user jobs shared by the local HTTP interface., Local web preferences and OS-managed credentials., pathlib, shutil, subprocess, sys, tempfile (+7 more)

### Community 23 - "image_generation.py"
Cohesion: 0.31
Nodes (8): generate_image(), image_type(), ImageModel, optimize_prompt(), Image generation and intent-preserving prompt preparation., selected_model(), base64, binascii

### Community 24 - "run-local.sh"
Cohesion: 0.40
Nodes (4): run-local.sh script, UV_CACHE_DIR, UV_NO_MODIFY_PATH, UV_PYTHON_INSTALL_DIR

### Community 25 - "BotState"
Cohesion: 0.17
Nodes (8): BotState, ImageJob, _run_image_job(), YouTube Persian subtitle Telegram bot., BotScopeTests, callbacks(), CommercialUiTests, ImageFlowTests

### Community 26 - "Path"
Cohesion: 0.29
Nodes (12): cleanup_expired_downloads(), _ffmpeg_preset(), _ffmpeg_threads(), _mux_dubbed_video(), publish_download(), publish_subtitle_player(), Path, Publish a no-transcode video bundle and a lightweight browser player. (+4 more)

### Community 27 - "handlers.py"
Cohesion: 0.06
Nodes (43): dataclasses, _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Grader (+35 more)

### Community 28 - "admin_callback"
Cohesion: 0.20
Nodes (15): admin_callback(), _bounded_percent(), _provider_label(), _show_admin_panel(), _show_model_options(), _show_model_settings(), _show_voice_options(), estimate_cents() (+7 more)

### Community 29 - "models.py"
Cohesion: 0.26
Nodes (10): filelock, download_whisper_model(), is_model_ready(), model_root(), Download and manage local multilingual faster-whisper models., config_path(), fake_download(), LocalWebModelsTests (+2 more)

### Community 30 - "test_conversation_progress.py"
Cohesion: 0.19
Nodes (6): PendingQuality, telegram_error, ConversationProgressTests, make_job(), DownloadOrderTests, OrderTests

### Community 31 - "server.py"
Cohesion: 0.29
Nodes (6): BaseHTTPRequestHandler, http_server, Handler, Private, single-job CPU audio separator for the bot's shared volume., run(), separate()

### Community 32 - "ModelSelection"
Cohesion: 0.33
Nodes (3): defaults(), ModelSelection, run()

### Community 34 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 35 - "app.js"
Cohesion: 0.39
Nodes (8): buildSettings(), fields, headings, loadSettings(), prefs, refresh(), request(), start()

## Knowledge Gaps
- **21 isolated node(s):** `ModelOption`, `fields`, `prefs`, `headings`, `run-local.sh script` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 239 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `worker`, `BotSetting`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `BotState`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `worker`, `Database`, `downloads.py`, `OrderHistoryTests`, `test_model_settings.py`, `process_video`, `admin_callback`, `test_conversation_progress.py`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `process_video()` connect `process_video` to `bot.py`, `worker`, `ModelSelection`, `test_subtitles.py`, `test_model_settings.py`, `app/pipeline.py`, `pathlib`, `image_generation.py`, `Path`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `Database` (e.g. with `BotState` and `_hydrate_order_titles()`) actually correct?**
  _`Database` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 13 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `fields`, `prefs` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06537530266343826 - nodes in this community are weakly interconnected._