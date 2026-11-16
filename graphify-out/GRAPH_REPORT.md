# Graph Report - yt  (2026-11-16)

## Corpus Check
- 39 files · ~47,117 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 667 nodes · 1905 edges · 21 communities (14 shown, 7 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 135 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `742bb785`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- downloads.py
- SubtitleTests
- database.py
- openai_limits.py
- app/pipeline.py
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- handlers.py
- Project agent guidance
- DatabaseIntegrationTests
- features/__init__.py
- worker
- video_captions/__init__.py
- WalletTransaction
- test_database_integration.py
- fonts/README.md
- .add_download
- test_video_captions.py
- image_generation.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 73 edges
2. `BotState` - 53 edges
3. `_state()` - 48 edges
4. `main()` - 47 edges
5. `button()` - 34 edges
6. `process_video()` - 32 edges
7. `_edit_query_screen()` - 27 edges
8. `worker()` - 25 edges
9. `back_keyboard()` - 24 edges
10. `JobCancelled` - 22 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `worker()` --uses--> `VideoCaptionJob`  [INFERRED]
  app/bot.py → features/video_captions/handlers.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `MinutePackage`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (21 total, 7 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.09
Nodes (95): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+87 more)

### Community 1 - "BotState"
Cohesion: 0.06
Nodes (34): admin_callback(), BotState, _bounded_percent(), ImageJob, PendingQuality, _provider_label(), _run_image_job(), _show_admin_panel() (+26 more)

### Community 4 - "downloads.py"
Cohesion: 0.08
Nodes (43): DownloadJob, _run_download_job(), _best_media_url(), classify_link(), _download_instagram_asset(), _download_instagram_media(), hook(), _download_instagram_profile_photo() (+35 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.12
Nodes (15): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+7 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.24
Nodes (10): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+2 more)

### Community 8 - "app/pipeline.py"
Cohesion: 0.05
Nodes (61): hydrate(), _audio_chunk_offsets(), _check_cancel(), _configure_realtime_speech(), _create_dubbed_audio(), generate(), _create_openrouter_dubbed_audio(), _download() (+53 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.13
Nodes (14): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+6 more)

### Community 10 - "handlers.py"
Cohesion: 0.06
Nodes (41): dataclasses, _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Grader (+33 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 15 - "worker"
Cohesion: 0.11
Nodes (32): _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init(), _progress_updater(), _publish_progress(), _publish_subtitle_player_link() (+24 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.22
Nodes (5): JobRecord, datetime, os, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 22 - "test_video_captions.py"
Cohesion: 0.08
Nodes (32): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., YouTube Persian subtitle Telegram bot., asyncio, BaseHTTPRequestHandler, http_server, importlib_util (+24 more)

### Community 23 - "image_generation.py"
Cohesion: 0.12
Nodes (17): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), generate_image(), image_type(), ImageModel (+9 more)

## Knowledge Gaps
- **14 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 193 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `database.py`, `DatabaseIntegrationTests`, `worker`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.197) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `downloads.py`, `worker`, `test_video_captions.py`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `process_video()` connect `app/pipeline.py` to `bot.py`, `BotState`, `SubtitleTests`, `worker`, `test_video_captions.py`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Database` (e.g. with `BotState` and `_hydrate_order_titles()`) actually correct?**
  _`Database` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09149484536082474 - nodes in this community are weakly interconnected._