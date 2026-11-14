# Graph Report - yt  (2026-11-14)

## Corpus Check
- 39 files · ~44,980 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: (none) 8, .separator 1, .conf 1)

## Summary
- 644 nodes · 1856 edges · 26 communities (19 shown, 7 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 132 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7fc4c5e2`
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
- _synthesize_fitting_dub
- ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب
- handlers.py
- Project agent guidance
- DatabaseIntegrationTests
- OpenRouterRateLimiter
- features/__init__.py
- app/pipeline.py
- video_captions/__init__.py
- process_video
- WalletTransaction
- test_database_integration.py
- .add_download
- test_video_captions.py
- image_generation.py
- test_subtitles.py
- Path

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
- `worker()` --uses--> `VideoCaptionJob`  [INFERRED]
  app/bot.py → features/video_captions/handlers.py
- `DatabaseIntegrationTests` --uses--> `JobRecord`  [INFERRED]
  tests/test_database_integration.py → app/database.py
- `DatabaseIntegrationTests` --uses--> `MinutePackage`  [INFERRED]
  tests/test_database_integration.py → app/database.py

## Import Cycles
- None detected.

## Communities (26 total, 7 thin omitted)

### Community 0 - "bot.py"
Cohesion: 0.09
Nodes (96): admin_callback(), admin_panel(), back_to_mode(), back_to_quality(), balance(), _bounded_percent(), cancel(), cancel_job_callback() (+88 more)

### Community 1 - "BotState"
Cohesion: 0.06
Nodes (29): BotState, ImageJob, PendingQuality, _run_image_job(), _show_model_options(), _show_model_settings(), defaults(), estimate_cents() (+21 more)

### Community 3 - "worker"
Cohesion: 0.18
Nodes (21): DownloadJob, _finish_progress(), Job, _job_refund_note(), _notify_admin_cost(), post_init(), _progress_updater(), _publish_progress() (+13 more)

### Community 4 - "downloads.py"
Cohesion: 0.07
Nodes (44): edit_subtitle_line(), generate_content(), request(), split_subtitle(), _best_media_url(), classify_link(), _download_instagram_asset(), _download_instagram_media() (+36 more)

### Community 5 - "SubtitleTests"
Cohesion: 0.11
Nodes (16): caption_cues(), _caption_parts(), _coverage(), _field(), _parts(), Readable Persian subtitle cues built from timed source speech., Pack complete words only when they fit into at most two lines., Ensure sequential short cues for SRT, VTT and the burned-in renderer. (+8 more)

### Community 6 - "database.py"
Cohesion: 0.11
Nodes (16): Base, BotSetting, CardTransferRequest, ContentOrder, DownloadTask, ImageOrder, PaymentOrder, PostgreSQL persistence for users, wallet ledger, transfer requests, jobs, and… (+8 more)

### Community 7 - "openai_limits.py"
Cohesion: 0.24
Nodes (10): get_openai_limits(), ModelLimit, OpenAILimitsUnavailable, _optional_int(), Response, _raise_for_admin_response(), Read-only OpenAI project limits and recent request usage via the Admin API., Fetch project rate limits and last-24h usage for the bot's API models. (+2 more)

### Community 8 - "_synthesize_fitting_dub"
Cohesion: 0.13
Nodes (9): _fit_dub_speech(), _shorten_dub_text(), _synthesize_fitting_dub(), AudioSegment, json, pydub, pydub_generators, PipelineTests (+1 more)

### Community 9 - "ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب"
Cohesion: 0.13
Nodes (14): HTTPS داخل Docker و انتقال از Nginx میزبان, اجرا با Docker, اجرای محلی بدون Docker, امکانات محتوایی، بسته‌های دقیقه و تیم, تنظیمات, دریافت از شبکه‌های اجتماعی, ربات تجاری تلگرام برای زیرنویس و دوبله فارسی یوتیوب, رفتار فعلی (+6 more)

### Community 10 - "handlers.py"
Cohesion: 0.06
Nodes (34): dataclasses, _escape(), _groups(), Path, Generate timed ASS captions with per-word highlighting., _time(), write_ass(), Grader (+26 more)

### Community 12 - "DatabaseIntegrationTests"
Cohesion: 0.13
Nodes (4): User, TelegramUser, DatabaseIntegrationTests, skipUnless

### Community 13 - "OpenRouterRateLimiter"
Cohesion: 0.29
Nodes (4): OpenRouterRateLimiter, Response, Conservative process-wide pacing plus provider Retry-After cooldowns., Request

### Community 15 - "app/pipeline.py"
Cohesion: 0.13
Nodes (18): Settings, cleanup(), _configure_realtime_speech(), get_available_qualities(), get_video_details(), OpenAICost, Probe a YouTube URL and return available heights and duration in seconds., Backward-compatible quality probe. (+10 more)

### Community 17 - "process_video"
Cohesion: 0.25
Nodes (14): _check_cancel(), _create_dubbed_audio(), generate(), _create_openrouter_dubbed_audio(), _download(), _dub_group_slot(), _make_dub_groups(), _media_duration() (+6 more)

### Community 19 - "test_database_integration.py"
Cohesion: 0.25
Nodes (4): JobRecord, datetime, Opt-in tests against a disposable PostgreSQL database only., uuid

### Community 22 - "test_video_captions.py"
Cohesion: 0.07
Nodes (33): _order_active_link(), datetime, Only expose a published token that belongs to this order and is still live., YouTube Persian subtitle Telegram bot., asyncio, BaseHTTPRequestHandler, http_server, importlib_util (+25 more)

### Community 23 - "image_generation.py"
Cohesion: 0.17
Nodes (14): Generate supplementary Persian content from existing subtitles., generate_image(), image_type(), ImageModel, optimize_prompt(), Image generation and intent-preserving prompt preparation., selected_model(), _openrouter_client() (+6 more)

### Community 24 - "test_subtitles.py"
Cohesion: 0.19
Nodes (11): _audio_chunk_offsets(), _isolate_ltr_runs(), Use the actual segment muxer boundaries, not nominal 8-minute offsets., Keep Latin words and number-like tokens in their natural LTR order., Write browser captions while preserving Persian/Latin bidirectional runs., _srt_time(), _transcribe(), _vtt_time() (+3 more)

### Community 25 - "Path"
Cohesion: 0.33
Nodes (9): cleanup_expired_downloads(), _mux_dubbed_video(), publish_download(), publish_subtitle_player(), Path, Publish a no-transcode video bundle and a lightweight browser player., _render(), _run() (+1 more)

## Knowledge Gaps
- **13 isolated node(s):** `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان`, `اجرا با Docker`, `مدل‌ها و صدای دوبله در پنل مدیر` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 182 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `bot.py`, `BotState`, `worker`, `database.py`, `DatabaseIntegrationTests`, `WalletTransaction`, `test_database_integration.py`, `.add_download`?**
  _High betweenness centrality (0.200) - this node is a cross-community bridge._
- **Why does `BotState` connect `BotState` to `bot.py`, `Database`, `worker`, `app/pipeline.py`, `test_video_captions.py`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `process_video()` connect `process_video` to `bot.py`, `BotState`, `worker`, `SubtitleTests`, `app/pipeline.py`, `test_video_captions.py`, `image_generation.py`, `test_subtitles.py`, `Path`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Database` (e.g. with `BotState` and `_publish_subtitle_player_link()`) actually correct?**
  _`Database` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BotState` (e.g. with `Settings` and `Database`) actually correct?**
  _`BotState` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ModelOption`, `Graphify`, `گراف کد برای توسعه‌دهندگان` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `bot.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09341468546181358 - nodes in this community are weakly interconnected._