# Graph Report - yt  (2026-11-12)

## Corpus Check
- 29 files · ~37,075 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 521 nodes · 1498 edges · 20 communities (15 shown, 5 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 111 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2ab7f80b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- worker
- test_downloads.py
- subtitles.py
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
- WalletTransaction
- test_database_integration.py
- .add_download
- SeparatorTests

## God Nodes (most connected - your core abstractions)
1. `Database` - 71 edges
2. `BotState` - 53 edges
3. `_state()` - 48 edges
4. `main()` - 46 edges
5. `process_video()` - 30 edges
6. `button()` - 25 edges
7. `worker()` - 22 edges
8. `Job` - 19 edges
9. `receive_link()` - 19 edges
10. `JobCancelled` - 18 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `ConversationProgressTests` --uses--> `BotState`  [INFERRED]
  tests/test_conversation_progress.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `DownloadOrderTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `OrderTests` --uses--> `BotState`  [INFERRED]
  tests/test_orders.py → app/bot.py

## Import Cycles
- None detected.

## Communities (20 total, 5 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.09
Nodes (88): admin_callback(), admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback() (+80 more)

### Community 1 - "BotState"
Cohesion: 0.06
Nodes (36): BotState, ImageJob, _run_image_job(), _show_model_options(), _show_model_settings(), YouTube Persian subtitle Telegram bot., defaults(), estimate_cents() (+28 more)

### Community 3 - "worker"
Cohesion: 0.12
Nodes (24): _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), PendingQuality, post_init(), _progress_updater(), _publish_progress() (+16 more)

### Community 4 - "test_downloads.py"
Cohesion: 0.15
Nodes (14): DownloadJob, _run_download_job(), classify_link(), download_media(), Path, Single-item download-only flows for supported public media links., Resolve one Spotify track to a labelled public YouTube search result., resolve_spotify_track() (+6 more)

### Community 5 - "subtitles.py"
Cohesion: 0.12
Nodes (16): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+8 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.22
Nodes (11): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+3 more)

### Community 8 - "pipeline.py"
Cohesion: 0.06
Nodes (60): load_settings(), Settings, _check_cancel(), cleanup(), cleanup_expired_downloads(), _configure_realtime_speech(), _create_dubbed_audio(), generate() (+52 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.14
Nodes (13): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+5 more)

### Community 10 - "JobCancelled"
Cohesion: 0.13
Nodes (18): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), hook(), generate_image(), image_type() (+10 more)

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
Cohesion: 0.23
Nodes (8): BaseHTTPRequestHandler, http_server, logging, Handler, Private, single-job CPU audio separator for the bot's shared volume., run(), separate(), threading

### Community 19 - "test_database_integration.py"
Cohesion: 0.25
Nodes (4): JobRecord, datetime, Opt-in tests against a disposable PostgreSQL database only., uuid

## Knowledge Gaps
- **12 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 143 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.247) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `worker`, `test_downloads.py`, `pipeline.py`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Why does `process_video()` connect `pipeline.py` to `bot.py`, `BotState`, `worker`, `subtitles.py`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09488139825218476 - nodes in this community are weakly interconnected._