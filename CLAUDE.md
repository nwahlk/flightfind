# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Installation & Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser (Chromium)
playwright install chromium

# Create config file from template
cp config.example.yaml config.yaml
# Then edit config.yaml with your settings
```

### Running the Application
```bash
# Run with default config (config.yaml)
python main.py

# Run with custom config path
python main.py path/to/config.yaml

# For debugging (disable headless mode in config.yaml)
# Set monitor.headless: false to see browser window
```

### Development & Testing
```bash
# Run tests
pytest

# Run tests with verbose output
pytest -v

# Format code with Black
black .

# Run specific test file
pytest tests/test_crawler.py
```

## Architecture Overview

FlightFind is an async Python application that monitors flight prices from Ctrip (携程) and sends alerts when prices drop below thresholds.

### Core Components

```
main.py (Entry point)
    │
    ├── FlightMonitor (Orchestrator)
    │       ├── Config (from config.py) - YAML configuration
    │       ├── Database (database.py) - SQLite with aiosqlite
    │       ├── CtripCrawler (crawler.py) - Playwright browser automation
    │       └── Notifier (notifier.py) - Email/Webhook/Bark notifications
    │
    └── src/
        ├── config.py - Dataclass-based config loading with validation
        ├── database.py - Async SQLite operations (price history, alerts, logs)
        ├── crawler.py - Playwright scraping with anti-bot detection
        ├── notifier.py - Multi-channel notification dispatch
        ├── exceptions.py - Custom exception hierarchy
        └── utils.py - Logging setup, retry decorator
```

### Key Design Patterns

1. **Async-First**: All I/O operations use `async/await`. Database uses `aiosqlite`, HTTP uses `aiohttp`.

2. **Configuration as Dataclasses**: `config.py` uses dataclasses with `from_dict()` factory methods. All config sections have corresponding dataclass types (Route, DateConfig, EmailConfig, etc.).

3. **Retry Pattern**: `@retry_with_backoff()` decorator provides exponential backoff with jitter. Used in crawler for browser init and search operations.

4. **Anti-Bot Detection**: Crawler checks for common anti-bot markers (captchas, sliders) and specific Chinese keywords before proceeding with scraping.

5. **Notification Deduplication**: Notifier maintains an in-memory `_history` set to prevent duplicate alerts for the same flight.

6. **Database Schema**: Three main tables:
   - `price_history` - All scraped flight prices
   - `low_price_alerts` - Alerts that triggered notifications
   - `execution_logs` - Job execution tracking

### Important Technical Details

- **Playwright Browser**: Single browser instance reused across requests. Page context is created once and reused.
- **City Codes**: The crawler currently uses raw city names in URLs (e.g., `from=深圳&to=上海`). This may need city-to-code mapping for production use.
- **No Scheduler**: Despite `APScheduler` being in requirements, the current implementation runs a single check and exits. No periodic scheduling is implemented yet.
- **Signal Handling**: SIGINT/SIGTERM handlers attempt graceful shutdown via `asyncio.create_task(monitor.close())`.
- **Notification Channels**: Email uses SMTP_SSL, Webhook sends WeChat/DingTalk format, Bark uses URL-encoded GET requests.

### Configuration Structure

`config.yaml` defines:
- `monitor.check_interval`: Minutes between checks (currently unused)
- `monitor.headless`: Whether to hide browser window
- `routes[]`: List of routes with from/to cities, price thresholds, and date configs
- `default_dates`: Fallback date config for routes without dates
- `notifications`: Email/webhook/bark settings (at least one must be enabled)

### Exception Hierarchy

```
FlightFindError (base)
├── ConfigError
├── DatabaseError
├── CrawlerError
│   ├── BrowserCrashError
│   ├── NetworkError
│   ├── TimeoutError
│   ├── ParseError
│   └── AntiBotError
└── NotifierError
```

When adding new error handling, prefer adding to this hierarchy rather than generic `Exception`.

### Working with the Crawler

The crawler uses multiple CSS selectors as fallbacks when parsing Ctrip's DOM. If Ctrip changes their page structure:
1. Add new selectors to the existing fallback lists in `_parse_flights()` and `_parse_single_flight()`
2. The crawler tries selectors in order until one matches elements

### Testing Considerations

- Tests should use `pytest-asyncio` for async test functions
- Mock Playwright browser operations in crawler tests
- Use temporary SQLite databases for database tests
- Test retry logic by triggering exceptions that match retryable types
