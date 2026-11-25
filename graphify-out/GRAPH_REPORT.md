# Graph Report - yt  (2026-11-26)

## Corpus Check
- 53 files · ~49,236 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: (none) 10, .separator 1, .conf 1)

## Summary
- 763 nodes · 2130 edges · 37 communities (26 shown, 11 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 133 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `124dc1ee`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- downloads.py
- subtitles.py
- database.py
- openai_limits.py
- _synthesize_fitting_dub
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- pathlib
- Project agent guidance
- DatabaseIntegrationTests
- MemoryDB
- features/__init__.py
- app/pipeline.py
- video_captions/__init__.py
- process_video
- WalletTransaction
- test_database_integration.py
- fonts/README.md
- server.py
- __main__.py
- service.py
- run-local.sh
- OpenRouterRateLimiter
- Path
- handlers.py
- .add_download
- models.py
- make_server
- LocalService
- test_subtitles.py
- _hydrate_order_titles
- app.js
- LocalWebHttpTests
- localweb/README.md
- tkinter

## God Nodes (most connected - your core abstractions)
1. `Database` - 73 edges
2. `BotState` - 59 edges
3. `_state()` - 48 edges
4. `main()` - 36 edges
5. `process_video()` - 34 edges
6. `button()` - 34 edges
7. `_edit_query_screen()` - 27 edges
8. `worker()` - 25 edges
9. `back_keyboard()` - 24 edges
10. `JobCancelled` - 22 edges

## Surprising Connections (you probably didn't know these)
- `MinuteEstimateTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py
- `ModelSettingsTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py
- `worker()` --uses--> `VideoCaptionJob`  [INFERRED]
  app/bot.py → features/video_captions/handlers.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `MinutePackage`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (37 total, 11 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.08
Nodes (107): admin_callback(), admin_panel(), back_to_mode(), back_to_quality(), balance(), _bounded_percent(), cancel(), cancel_job_callback() (+99 more)

### Community 1 - "BotState"
Cohesion: 0.05
Nodes (45): BotState, DownloadJob, _finish_progress(), ImageJob, Job, _job_refund_note(), _notify_admin_cost(), PendingQuality (+37 more)

### Community 4 - "downloads.py"
Cohesion: 0.06
Nodes (46): edit_subtitle_line(), generate_content(), request(), split_subtitle(), _best_media_url(), classify_link(), _download_instagram_asset(), _download_instagram_media() (+38 more)

### Community 5 - "subtitles.py"
Cohesion: 0.15
Nodes (13): _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Interpolate only when a provider has no usable word timestamps., Return speech-sized source cues, using word times only if complete. (+5 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.24
Nodes (10): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+2 more)

### Community 8 - "_synthesize_fitting_dub"
Cohesion: 0.15
Nodes (6): _fit_dub_speech(), _shorten_dub_text(), _synthesize_fitting_dub(), AudioSegment, PipelineTests, answer()

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.15
Nodes (12): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, بسته‌های دقیقه, تنظیمات, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی, زیرنویس انیمیشنی ویدیوی ارسالی (+4 more)

### Community 10 - "pathlib"
Cohesion: 0.07
Nodes (34): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., YouTube Persian subtitle Telegram bot., asyncio, importlib_util, io, config_path() (+26 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "MemoryDB"
Cohesion: 0.21
Nodes (4): MemoryDB, MinuteEstimateTests, ModelSettingsTests, settings()

### Community 15 - "app/pipeline.py"
Cohesion: 0.09
Nodes (32): Settings, Generate supplementary Persian content from existing subtitles., cleanup(), _configure_realtime_speech(), get_available_qualities(), get_video_details(), get_video_details_with_title(), _isolate_ltr_runs() (+24 more)

### Community 17 - "process_video"
Cohesion: 0.21
Nodes (16): _check_cancel(), _create_dubbed_audio(), generate(), _create_openrouter_dubbed_audio(), _download(), _dub_group_slot(), _make_dub_groups(), _media_duration() (+8 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.25
Nodes (4): JobRecord, datetime, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 21 - "server.py"
Cohesion: 0.29
Nodes (6): BaseHTTPRequestHandler, http_server, Handler, Private, single-job CPU audio separator for the bot's shared volume., run(), separate()

### Community 22 - "__main__.py"
Cohesion: 0.22
Nodes (9): argparse, hmac, http_client, json, Start the local-only web application with ``python -m localweb``., secrets, threading, urllib_parse (+1 more)

### Community 23 - "service.py"
Cohesion: 0.20
Nodes (10): generate_image(), image_type(), ImageModel, optimize_prompt(), Image generation and intent-preserving prompt preparation., selected_model(), base64, binascii (+2 more)

### Community 24 - "run-local.sh"
Cohesion: 0.40
Nodes (4): run-local.sh script, UV_CACHE_DIR, UV_NO_MODIFY_PATH, UV_PYTHON_INSTALL_DIR

### Community 25 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 26 - "Path"
Cohesion: 0.36
Nodes (8): _ffmpeg_preset(), _ffmpeg_threads(), _mux_dubbed_video(), Path, _render(), _run(), _watermark_filter(), FFmpegEfficiencyTests

### Community 27 - "handlers.py"
Cohesion: 0.06
Nodes (36): dataclasses, _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Grader (+28 more)

### Community 29 - "models.py"
Cohesion: 0.28
Nodes (9): filelock, download_whisper_model(), is_model_ready(), model_root(), Download and manage local multilingual faster-whisper models., fake_download(), LocalWebModelsTests, cancelled() (+1 more)

### Community 30 - "make_server"
Cohesion: 0.39
Nodes (6): main(), make_server(), do_GET(), do_POST(), respond(), valid_host()

### Community 32 - "test_subtitles.py"
Cohesion: 0.14
Nodes (10): defaults(), ModelSelection, _audio_chunk_offsets(), Use the actual segment muxer boundaries, not nominal 8-minute offsets., _transcribe(), caption_cues(), Ensure sequential short cues for SRT, VTT and the burned-in renderer., httpx (+2 more)

### Community 34 - "_hydrate_order_titles"
Cohesion: 0.40
Nodes (5): _hydrate_order_titles(), hydrate(), Backfill missing titles from public YouTube metadata, without cookies., get_public_youtube_title(), Best-effort title lookup for old orders, without using account cookies.

### Community 35 - "app.js"
Cohesion: 0.39
Nodes (8): buildSettings(), fields, headings, loadSettings(), prefs, refresh(), request(), start()

## Knowledge Gaps
- **20 isolated node(s):** `ModelOption`, `fields`, `prefs`, `headings`, `run-local.sh script` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 221 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `_hydrate_order_titles`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.169) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `pathlib`, `MemoryDB`, `app/pipeline.py`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `process_video()` connect `process_video` to `bot.py`, `BotState`, `test_subtitles.py`, `pathlib`, `MemoryDB`, `app/pipeline.py`, `service.py`, `Path`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Database` (e.g. with `BotState` and `_hydrate_order_titles()`) actually correct?**
  _`Database` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 13 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `fields`, `prefs` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07900101936799185 - nodes in this community are weakly interconnected._