# Graph Report - yt  (2026-11-14)

## Corpus Check
- 29 files · ~39,997 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 560 nodes · 1630 edges · 18 communities (14 shown, 4 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 115 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4c86d92a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- worker
- downloads.py
- SubtitleTests
- database.py
- openai_limits.py
- pipeline.py
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- image_generation.py
- Project agent guidance
- DatabaseIntegrationTests
- OpenRouterRateLimiter
- test_downloads.py
- WalletTransaction
- test_database_integration.py
- .add_download

## God Nodes (most connected - your core abstractions)
1. `Database` - 71 edges
2. `BotState` - 53 edges
3. `_state()` - 48 edges
4. `main()` - 46 edges
5. `process_video()` - 32 edges
6. `button()` - 31 edges
7. `_edit_query_screen()` - 25 edges
8. `worker()` - 23 edges
9. `back_keyboard()` - 23 edges
10. `JobCancelled` - 22 edges

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

## Communities (18 total, 4 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.10
Nodes (90): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+82 more)

### Community 1 - "BotState"
Cohesion: 0.06
Nodes (32): admin_callback(), BotState, _bounded_percent(), ImageJob, PendingQuality, _provider_label(), _run_image_job(), _safe_edit() (+24 more)

### Community 3 - "worker"
Cohesion: 0.18
Nodes (21): DownloadJob, _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init(), _progress_updater(), _publish_progress() (+13 more)

### Community 4 - "downloads.py"
Cohesion: 0.10
Nodes (28): _best_media_url(), classify_link(), _download_instagram_asset(), _download_instagram_media(), hook(), download_media(), hook(), _instagram_cookie_options() (+20 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.11
Nodes (17): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+9 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.22
Nodes (11): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+3 more)

### Community 8 - "pipeline.py"
Cohesion: 0.05
Nodes (65): load_settings(), Settings, defaults(), ModelSelection, _audio_chunk_offsets(), _check_cancel(), cleanup(), cleanup_expired_downloads() (+57 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.14
Nodes (13): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+5 more)

### Community 10 - "image_generation.py"
Cohesion: 0.14
Nodes (15): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), generate_image(), image_type(), ImageModel (+7 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 15 - "test_downloads.py"
Cohesion: 0.07
Nodes (31): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., YouTube Persian subtitle Telegram bot., asyncio, BaseHTTPRequestHandler, http_server, json (+23 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.25
Nodes (4): JobRecord, datetime, Opt-in tests against a disposable PostgreSQL database only., uuid

## Knowledge Gaps
- **12 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 155 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.232) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `worker`, `pipeline.py`, `test_downloads.py`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `process_video()` connect `pipeline.py` to `bot.py`, `BotState`, `worker`, `SubtitleTests`, `test_downloads.py`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0981844242713808 - nodes in this community are weakly interconnected._