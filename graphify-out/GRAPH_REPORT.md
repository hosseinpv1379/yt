# Graph Report - yt  (2026-11-14)

## Corpus Check
- 39 files · ~46,941 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 664 nodes · 1898 edges · 26 communities (19 shown, 7 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 135 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e85c17bc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- bot.py
- BotState
- Database
- admin_callback
- downloads.py
- subtitles.py
- database.py
- openai_limits.py
- _synthesize_fitting_dub
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- handlers.py
- Project agent guidance
- DatabaseIntegrationTests
- _hydrate_order_titles
- features/__init__.py
- app/pipeline.py
- video_captions/__init__.py
- process_video
- WalletTransaction
- test_database_integration.py
- fonts/README.md
- .add_download
- pathlib
- image_generation.py
- test_subtitles.py
- Path

## God Nodes (most connected - your core abstractions)
1. `Database` - 73 edges
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
- `DownloadDeliveryTests` --uses--> `BotState`  [INFERRED]
  tests/test_downloads.py → app/bot.py
- `MinuteEstimateTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py
- `ModelSettingsTests` --uses--> `BotState`  [INFERRED]
  tests/test_model_settings.py → app/bot.py
- `worker()` --uses--> `VideoCaptionJob`  [INFERRED]
  app/bot.py → features/video_captions/handlers.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (26 total, 7 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.10
Nodes (92): admin_panel(), back_to_mode(), back_to_quality(), balance(), cancel(), cancel_job_callback(), cancel_order_callback(), _cancel_requested_text() (+84 more)

### Community 1 - "BotState"
Cohesion: 0.08
Nodes (31): BotState, _finish_progress(), ImageJob, Job, _job_refund_note(), _notify_admin_cost(), PendingQuality, post_init() (+23 more)

### Community 3 - "admin_callback"
Cohesion: 0.10
Nodes (21): admin_callback(), _bounded_percent(), _provider_label(), _show_admin_panel(), _show_model_options(), _show_model_settings(), _show_voice_options(), defaults() (+13 more)

### Community 4 - "downloads.py"
Cohesion: 0.08
Nodes (45): DownloadJob, _run_download_job(), _best_media_url(), classify_link(), _download_instagram_asset(), _download_instagram_media(), hook(), _download_instagram_profile_photo() (+37 more)

### Community 5 - "subtitles.py"
Cohesion: 0.15
Nodes (13): _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Interpolate only when a provider has no usable word timestamps., Return speech-sized source cues, using word times only if complete. (+5 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.22
Nodes (11): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+3 more)

### Community 8 - "_synthesize_fitting_dub"
Cohesion: 0.13
Nodes (9): _fit_dub_speech(), _shorten_dub_text(), _synthesize_fitting_dub(), AudioSegment, json, pydub, pydub_generators, PipelineTests (+1 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.13
Nodes (14): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+6 more)

### Community 10 - "handlers.py"
Cohesion: 0.06
Nodes (43): dataclasses, _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Grader (+35 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "_hydrate_order_titles"
Cohesion: 0.40
Nodes (5): _hydrate_order_titles(), hydrate(), Backfill missing titles from public YouTube metadata, without cookies., get_public_youtube_title(), Best-effort title lookup for old orders, without using account cookies.

### Community 15 - "app/pipeline.py"
Cohesion: 0.10
Nodes (23): load_settings(), Settings, cleanup(), _configure_realtime_speech(), get_available_qualities(), get_video_details(), get_video_details_with_title(), OpenAICost (+15 more)

### Community 17 - "process_video"
Cohesion: 0.24
Nodes (15): _check_cancel(), _create_dubbed_audio(), generate(), _create_openrouter_dubbed_audio(), _download(), _dub_group_slot(), _make_dub_groups(), _media_duration() (+7 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.22
Nodes (5): JobRecord, datetime, os, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 22 - "pathlib"
Cohesion: 0.07
Nodes (30): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., YouTube Persian subtitle Telegram bot., asyncio, BaseHTTPRequestHandler, http_server, importlib_util (+22 more)

### Community 23 - "image_generation.py"
Cohesion: 0.10
Nodes (20): edit_subtitle_line(), generate_content(), request(), Generate supplementary Persian content from existing subtitles., split_subtitle(), generate_image(), image_type(), ImageModel (+12 more)

### Community 24 - "test_subtitles.py"
Cohesion: 0.12
Nodes (14): ModelSelection, _audio_chunk_offsets(), _isolate_ltr_runs(), Use the actual segment muxer boundaries, not nominal 8-minute offsets., Keep Latin words and number-like tokens in their natural LTR order., Write browser captions while preserving Persian/Latin bidirectional runs., _transcribe(), _vtt_time() (+6 more)

### Community 25 - "Path"
Cohesion: 0.39
Nodes (7): _mux_dubbed_video(), publish_subtitle_player(), Path, Publish a no-transcode video bundle and a lightweight browser player., _render(), _run(), _watermark_filter()

## Knowledge Gaps
- **14 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 192 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `database.py`, `DatabaseIntegrationTests`, `_hydrate_order_titles`, `app/pipeline.py`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `admin_callback`, `downloads.py`, `app/pipeline.py`, `pathlib`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `process_video()` connect `process_video` to `bot.py`, `BotState`, `admin_callback`, `app/pipeline.py`, `pathlib`, `test_subtitles.py`, `Path`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Database` (e.g. with `BotState` and `_hydrate_order_titles()`) actually correct?**
  _`Database` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09631663234957676 - nodes in this community are weakly interconnected._