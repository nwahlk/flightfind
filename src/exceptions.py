"""Project exception types."""


class FlightFindError(Exception):
    """Base exception for the project."""


class ConfigError(FlightFindError):
    """Configuration error."""


class DatabaseError(FlightFindError):
    """Database error."""


class CrawlerError(FlightFindError):
    """Crawler error."""


class BrowserCrashError(CrawlerError):
    """Browser startup or runtime error."""


class ParseError(CrawlerError):
    """Response parsing error."""


class AntiBotError(CrawlerError):
    """Anti-bot or risk-control error."""


class NotifierError(FlightFindError):
    """Notification sending error."""
