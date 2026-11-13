# Graph Report - yt  (2026-11-13)

## Corpus Check
- 29 files · ~38,247 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 535 nodes · 1528 edges · 21 communities (16 shown, 5 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 114 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4f48fede`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- worker
- test_downloads.py
- SubtitleTests
- database.py
- openai_limits.py
- pipeline.py
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- JobCancelled
- Project agent guidance
- DatabaseIntegrationTests
- OpenRouterRateLimiter
- _order_active_link
- server.py
- admin_callback
- WalletTransaction
- test_database_integration.py
- .add_download
- SeparatorTests

## God Nodes (most connected - your core abstractions)
1. `Database` - 71 edges
2. `BotState` - 53 edges
3. `_state()` - 48 edges
4. `main()` - 46 edges
5. `process_video()` - 32 edges
6. `button()` - 25 edges
7. `worker()` - 22 edges
8. `Job` - 19 edges
9. `receive_link()` - 19 edges
10. `JobCancelled` - 18 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `MinutePackage`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `Database`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (21 total, 5 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.10
Nodes (85): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+77 more)

### Community 1 - "BotState"
Cohesion: 0.07
Nodes (28): BotState, ImageJob, PendingQuality, _run_image_job(), YouTube Persian subtitle Telegram bot., pathlib, shutil, subprocess (+20 more)

### Community 3 - "worker"
Cohesion: 0.19
Nodes (19): _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init(), _progress_updater(), _publish_progress(), _publish_subtitle_player_link() (+11 more)

### Community 4 - "test_downloads.py"
Cohesion: 0.14
Nodes (15): DownloadJob, _run_download_job(), classify_link(), download_media(), hook(), Path, Single-item download-only flows for supported public media links., Resolve one Spotify track to a labelled public YouTube search result. (+7 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.11
Nodes (16): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+8 more)

### Community 6 - "database.py"
Cohesion: 0.12
Nodes (15): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+7 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.22
Nodes (11): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+3 more)

### Community 8 - "pipeline.py"
Cohesion: 0.06
Nodes (63): load_settings(), Settings, _audio_chunk_offsets(), _check_cancel(), cleanup(), _configure_realtime_speech(), _create_dubbed_audio(), generate() (+55 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.14
Nodes (13): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+5 more)

### Community 10 - "JobCancelled"
Cohesion: 0.13
Nodes (18): _run_content_job(), edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), generate_image(), image_type() (+10 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 14 - "_order_active_link"
Cohesion: 0.40
Nodes (4): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., OrderLinkTests

### Community 15 - "server.py"
Cohesion: 0.21
Nodes (9): BaseHTTPRequestHandler, http_server, logging, re, Handler, Private, single-job CPU audio separator for the bot's shared volume., run(), separate() (+1 more)

### Community 17 - "admin_callback"
Cohesion: 0.16
Nodes (17): admin_callback(), _provider_label(), _show_admin_panel(), _show_model_options(), _show_model_settings(), _show_voice_options(), defaults(), estimate_cents() (+9 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.29
Nodes (5): MinutePackage, datetime, os, Opt-in tests against a disposable PostgreSQL database only., uuid

## Knowledge Gaps
- **12 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 147 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `pipeline.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.241) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `worker`, `test_downloads.py`, `pipeline.py`, `JobCancelled`, `admin_callback`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `process_video()` connect `pipeline.py` to `bot.py`, `BotState`, `worker`, `SubtitleTests`, `admin_callback`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09703287890938252 - nodes in this community are weakly interconnected._