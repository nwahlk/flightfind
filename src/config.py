"""
Application configuration models and loader.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Literal, Union

import yaml

from src.exceptions import ConfigError


AIRPORT_NAMES = {
    "PEK": "Beijing Capital",
    "PKX": "Beijing Daxing",
    "BJS": "Beijing",
    "SHA": "Shanghai Hongqiao",
    "PVG": "Shanghai Pudong",
    "SHA-CITY": "Shanghai",
    "CAN": "Guangzhou Baiyun",
    "SZX": "Shenzhen Bao'an",
    "CTU": "Chengdu Tianfu/Shuangliu",
    "TFU": "Chengdu Tianfu",
    "XIY": "Xi'an Xianyang",
    "CKG": "Chongqing Jiangbei",
    "NKG": "Nanjing Lukou",
    "WUH": "Wuhan Tianhe",
    "TSN": "Tianjin Binhai",
    "TAO": "Qingdao Jiaodong",
    "DLC": "Dalian Zhoushuizi",
    "XMN": "Xiamen Gaoqi",
    "KMG": "Kunming Changshui",
    "CSX": "Changsha Huanghua",
    "CGO": "Zhengzhou Xinzheng",
    "SHE": "Shenyang Taoxian",
    "TNA": "Jinan Yaoqiang",
    "HRB": "Harbin Taiping",
    "SYX": "Sanya Phoenix",
    "HAK": "Haikou Meilan",
    "FOC": "Fuzhou Changle",
    "NNG": "Nanning Wuxu",
}


@dataclass
class DateConfig:
    """Date selection for a route."""

    mode: Literal["absolute", "relative"] = "absolute"
    absolute_dates: List[date] = field(default_factory=list)
    relative_days: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "DateConfig":
        if not data:
            return cls()

        mode = data.get("mode", "absolute")
        if mode == "absolute":
            dates: List[date] = []
            for value in data.get("absolute_dates", []):
                if isinstance(value, date):
                    dates.append(value)
                elif isinstance(value, str):
                    dates.append(date.fromisoformat(value))
            return cls(mode=mode, absolute_dates=dates)

        return cls(mode=mode, relative_days=data.get("relative_days", []))


@dataclass
class Route:
    """One monitored route."""

    from_city: str
    to_city: str
    low_price_threshold: int
    dates: DateConfig

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        return cls(
            from_city=data["from"],
            to_city=data["to"],
            low_price_threshold=data["low_price_threshold"],
            dates=DateConfig.from_dict(data.get("dates", {})),
        )


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 465
    username: str = ""
    password: str = ""
    to: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "EmailConfig":
        return cls(
            enabled=data.get("enabled", False),
            smtp_server=data.get("smtp_server", ""),
            smtp_port=data.get("smtp_port", 465),
            username=data.get("username", ""),
            password=data.get("password", ""),
            to=data.get("to", []),
        )


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookConfig":
        return cls(
            enabled=data.get("enabled", False),
            url=data.get("url", ""),
        )


@dataclass
class BarkConfig:
    enabled: bool = False
    device_key: str = ""
    server: str = "https://api.day.app"

    @classmethod
    def from_dict(cls, data: dict) -> "BarkConfig":
        return cls(
            enabled=data.get("enabled", False),
            device_key=data.get("device_key", ""),
            server=data.get("server", "https://api.day.app"),
        )


@dataclass
class MonitorConfig:
    check_interval: int = 30
    headless: bool = True
    default_source: str = "feizhu"
    feizhu_username: str = ""
    feizhu_password: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorConfig":
        return cls(
            check_interval=data.get("check_interval", 30),
            headless=data.get("headless", True),
            default_source=data.get("default_source", "feizhu"),
            feizhu_username=data.get("feizhu_username", ""),
            feizhu_password=data.get("feizhu_password", ""),
        )


@dataclass
class CaptchaConfig:
    type: str = "none"
    chaojiying_username: str = ""
    chaojiying_password: str = ""
    chaojiying_soft_id: str = "96001"

    @classmethod
    def from_dict(cls, data: dict) -> "CaptchaConfig":
        if not data:
            return cls()
        return cls(
            type=data.get("type", "none"),
            chaojiying_username=data.get("chaojiying_username", ""),
            chaojiying_password=data.get("chaojiying_password", ""),
            chaojiying_soft_id=data.get("chaojiying_soft_id", "96001"),
        )


@dataclass
class NotificationsConfig:
    email: EmailConfig
    webhook: WebhookConfig
    bark: BarkConfig

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationsConfig":
        return cls(
            email=EmailConfig.from_dict(data.get("email", {})),
            webhook=WebhookConfig.from_dict(data.get("webhook", {})),
            bark=BarkConfig.from_dict(data.get("bark", {})),
        )


@dataclass
class AppConfig:
    monitor: MonitorConfig
    routes: List[Route]
    default_dates: DateConfig
    notifications: NotificationsConfig
    captcha: CaptchaConfig = None

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(
            monitor=MonitorConfig.from_dict(data.get("monitor", {})),
            routes=[Route.from_dict(item) for item in data.get("routes", [])],
            default_dates=DateConfig.from_dict(data.get("default_dates", {})),
            notifications=NotificationsConfig.from_dict(data.get("notifications", {})),
            captcha=CaptchaConfig.from_dict(data.get("captcha", {})),
        )


def load_config(config_path: Union[str, Path]) -> AppConfig:
    """Load and validate application config from YAML."""

    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read config: {exc}") from exc

    if not data:
        raise ConfigError("Config file is empty")

    config = AppConfig.from_dict(data)
    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    valid_sources = {"csair", "ctrip", "feizhu", "spring", "mu", "zh", "ho"}
    if config.monitor.default_source not in valid_sources:
        raise ConfigError(
            f"default_source must be one of {sorted(valid_sources)}, "
            f"got: {config.monitor.default_source}"
        )

    if not config.routes:
        raise ConfigError("At least one route must be configured")

    for index, route in enumerate(config.routes, start=1):
        if not route.from_city or not route.to_city:
            raise ConfigError(f"Route {index}: both from/to are required")
        if route.low_price_threshold <= 0:
            raise ConfigError(f"Route {index}: low_price_threshold must be greater than 0")
        if not route.dates.absolute_dates and not route.dates.relative_days:
            raise ConfigError(f"Route {index}: at least one date must be configured")

    has_notification = (
        config.notifications.email.enabled
        or config.notifications.webhook.enabled
        or config.notifications.bark.enabled
    )
    if not has_notification:
        raise ConfigError("At least one notification channel must be enabled")


def get_airport_name(code: str) -> str:
    """Return a friendly airport name for notifier compatibility."""

    if not code:
        return ""
    return AIRPORT_NAMES.get(code.upper(), code)
