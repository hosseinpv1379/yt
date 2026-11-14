# Graph Report - yt  (2026-11-14)

## Corpus Check
- 29 files · ~38,587 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 543 nodes · 1588 edges · 17 communities (13 shown, 4 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 114 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `aba44264`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- worker
- JobCancelled
- SubtitleTests
- database.py
- image_generation.py
- pipeline.py
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- orders_callback
- Project agent guidance
- DatabaseIntegrationTests
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
10. `Job` - 19 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `OrderHistoryTests` --uses--> `BotState`  [INFERRED]
  tests/test_order_history.py → app/bot.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `MinutePackage`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (17 total, 4 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.10
Nodes (88): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+80 more)

### Community 1 - "BotState"
Cohesion: 0.06
Nodes (36): admin_callback(), BotState, _bounded_percent(), ImageJob, PendingQuality, _provider_label(), _run_image_job(), _safe_edit() (+28 more)

### Community 3 - "worker"
Cohesion: 0.10
Nodes (33): DownloadJob, _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init(), _progress_updater(), _publish_progress() (+25 more)

### Community 4 - "JobCancelled"
Cohesion: 0.07
Nodes (26): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), classify_link(), download_media(), hook() (+18 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.10
Nodes (18): _srt_time(), _write_srt(), caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech. (+10 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "image_generation.py"
Cohesion: 0.13
Nodes (19): generate_image(), image_type(), ImageModel, optimize_prompt(), Image generation and intent-preserving prompt preparation., selected_model(), get_openai_limits(), ModelLimit (+11 more)

### Community 8 - "pipeline.py"
Cohesion: 0.07
Nodes (47): _audio_chunk_offsets(), _check_cancel(), _configure_realtime_speech(), _create_dubbed_audio(), generate(), _create_openrouter_dubbed_audio(), _download(), _dub_group_slot() (+39 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.14
Nodes (13): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+5 more)

### Community 10 - "orders_callback"
Cohesion: 0.23
Nodes (7): _order_active_link(), _order_kind(), orders_callback(), datetime, Only expose a published token that belongs to this order and is still live., OrderHistoryTests, OrderLinkTests

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 15 - "test_downloads.py"
Cohesion: 0.10
Nodes (24): YouTube Persian subtitle Telegram bot., asyncio, BaseHTTPRequestHandler, http_server, json, logging, pathlib, pydub_generators (+16 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.29
Nodes (5): MinutePackage, datetime, os, Opt-in tests against a disposable PostgreSQL database only., uuid

## Knowledge Gaps
- **12 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 149 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.238) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `worker`, `orders_callback`, `test_downloads.py`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `process_video()` connect `pipeline.py` to `bot.py`, `BotState`, `worker`, `SubtitleTests`, `test_downloads.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _12 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10012484394506867 - nodes in this community are weakly interconnected._