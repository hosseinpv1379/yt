# Graph Report - yt  (2026-11-14)

## Corpus Check
- 38 files · ~44,366 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 638 nodes · 1839 edges · 33 communities (22 shown, 11 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 131 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `71b458d0`
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
- app/pipeline.py
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- handlers.py
- Project agent guidance
- DatabaseIntegrationTests
- OpenRouterRateLimiter
- features/__init__.py
- server.py
- video_captions/__init__.py
- model_catalog.py
- WalletTransaction
- test_database_integration.py
- .add_download
- test_model_settings.py
- test_video_captions.py
- _order_active_link
- MemoryDB
- .test_raw_frame_render_preserves_audio
- test_image_generation.py
- write_ass
- tempfile
- TranscriptionTests
- OrderHistoryTests
- InputFlowTests

## God Nodes (most connected - your core abstractions)
1. `Database` - 71 edges
2. `BotState` - 53 edges
3. `_state()` - 48 edges
4. `main()` - 47 edges
5. `button()` - 34 edges
6. `process_video()` - 32 edges
7. `_edit_query_screen()` - 25 edges
8. `worker()` - 25 edges
9. `back_keyboard()` - 24 edges
10. `JobCancelled` - 22 edges

## Surprising Connections (you probably didn't know these)
- `CommercialUiTests` --uses--> `Job`  [INFERRED]
  tests/test_commercial_ui.py → app/bot.py
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `ImageFlowTests` --uses--> `BotState`  [INFERRED]
  tests/test_image_generation.py → app/bot.py
- `MinuteEstimateTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py
- `ModelSettingsTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py

## Import Cycles
- None detected.

## Communities (33 total, 11 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.10
Nodes (90): admin_callback(), admin_panel(), back_to_mode(), back_to_quality(), balance(), _bounded_percent(), cancel(), cancel_job_callback() (+82 more)

### Community 1 - "BotState"
Cohesion: 0.17
Nodes (8): BotState, PendingQuality, _safe_edit(), CommercialUiTests, ConversationProgressTests, make_job(), DownloadOrderTests, OrderTests

### Community 3 - "worker"
Cohesion: 0.11
Nodes (31): _cancel_requested_text(), ContentJob, DownloadJob, _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init() (+23 more)

### Community 4 - "downloads.py"
Cohesion: 0.07
Nodes (43): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), _best_media_url(), classify_link(), _download_instagram_asset() (+35 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.11
Nodes (17): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+9 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.24
Nodes (10): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+2 more)

### Community 8 - "app/pipeline.py"
Cohesion: 0.05
Nodes (69): load_settings(), Settings, generate_image(), image_type(), ImageModel, optimize_prompt(), Image generation and intent-preserving prompt preparation., selected_model() (+61 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.13
Nodes (14): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+6 more)

### Community 10 - "handlers.py"
Cohesion: 0.16
Nodes (16): dataclasses, Grader, GradeSettings, CPU person segmentation and temporally smoothed color grading., callback(), _pending(), _quote(), Telegram workflow for offline caption and color jobs. (+8 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 15 - "server.py"
Cohesion: 0.25
Nodes (7): BaseHTTPRequestHandler, http_server, logging, Handler, Private, single-job CPU audio separator for the bot's shared volume., run(), separate()

### Community 17 - "model_catalog.py"
Cohesion: 0.18
Nodes (11): _show_model_options(), _show_model_settings(), defaults(), estimate_cents(), format_dollars(), load_selection(), ModelOption, ModelSelection (+3 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.29
Nodes (5): MinutePackage, datetime, os, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 22 - "test_model_settings.py"
Cohesion: 0.23
Nodes (7): YouTube Persian subtitle Telegram bot., telegram_error, CostDisplayTests, KeyboardTests, types, unittest, unittest_mock

### Community 23 - "test_video_captions.py"
Cohesion: 0.22
Nodes (12): Offline captions and one-pass video rendering for uploaded videos., _model(), Path, Local speech recognition with one lazily loaded CPU model per process., transcribe(), functools, importlib_util, io (+4 more)

### Community 24 - "_order_active_link"
Cohesion: 0.40
Nodes (4): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., OrderLinkTests

### Community 25 - "MemoryDB"
Cohesion: 0.21
Nodes (4): MemoryDB, MinuteEstimateTests, ModelSettingsTests, settings()

### Community 27 - "test_image_generation.py"
Cohesion: 0.38
Nodes (5): ImageJob, _run_image_job(), StageSelection, ImageApiTests, ImageFlowTests

### Community 28 - "write_ass"
Cohesion: 0.36
Nodes (8): _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Word, CaptionBuilderTests

### Community 29 - "tempfile"
Cohesion: 0.22
Nodes (7): shutil, subprocess, tempfile, DubMixingTests, skipUnless, skipUnless, SeparatorTests

## Knowledge Gaps
- **13 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 183 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `app/pipeline.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `InputFlowTests`, `Database`, `worker`, `app/pipeline.py`, `model_catalog.py`, `test_model_settings.py`, `MemoryDB`, `test_image_generation.py`, `OrderHistoryTests`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `process_video()` connect `app/pipeline.py` to `bot.py`, `worker`, `SubtitleTests`, `model_catalog.py`, `test_model_settings.py`, `MemoryDB`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10176779741997133 - nodes in this community are weakly interconnected._