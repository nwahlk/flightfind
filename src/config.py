"""
配置管理模块
"""

from dataclasses import dataclass, field

AIRPORT_NAMES = {
    'PEK': '北京首都', 'PKX': '大兴',
    'SHA': '虹桥', 'PVG': '浦东',
    'CAN': '白云', 'SZX': '宝安',
    'CTU': '双流', 'KMG': '长水',
    'XIY': '咸阳', 'CKG': '江北',
    'TAO': '胶东', 'TSN': '滨海',
    'DLC': '大连', 'XMN': '厦门',
    'KMG': '昆明', 'CSX': '长沙',
    'CGO': '郑州', 'SHE': '沈阳',
    'TNA': '济南', 'HRB': '哈尔滨',
    'SYX': '三亚', 'HAK': '海口', 'FOC': '福州',
    'NNG': '南宁', 'KWE': '贵阳', 'LHW': '银川',
    'INC': '西宁', 'XNN': '拉萨', 'URC': '呼和浩特',
    'SJW': '石家庄', 'TYN': '长春', 'CGQ': '温州',
    'WNZ': '宁波', 'HFE': '合肥', 'KHN': '南昌',
    'KWL': '桂林', 'LJG': '丽江'
}
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional, Union
import yaml
from src.exceptions import ConfigError


@dataclass
class DateConfig:
    """日期配置"""
    mode: Literal["absolute", "relative"] = "absolute"
    absolute_dates: List[date] = field(default_factory=list)
    relative_days: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "DateConfig":
        if not data:
            return cls()

        mode = data.get("mode", "absolute")

        if mode == "absolute":
            date_strings = data.get("absolute_dates", [])
            dates = []
            for d in date_strings:
                if isinstance(d, str):
                    dates.append(date.fromisoformat(d))
                elif isinstance(d, date):
                    dates.append(d)
            return cls(mode=mode, absolute_dates=dates)
        else:
            return cls(
                mode=mode,
                relative_days=data.get("relative_days", [])
            )


@dataclass
class Route:
    """航线配置"""
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
            dates=DateConfig.from_dict(data.get("dates", {}))
        )


@dataclass
class EmailConfig:
    """邮件配置"""
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
            to=data.get("to", [])
        )


@dataclass
class WebhookConfig:
    """Webhook配置"""
    enabled: bool = False
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookConfig":
        return cls(
            enabled=data.get("enabled", False),
            url=data.get("url", "")
        )


@dataclass
class BarkConfig:
    """Bark配置"""
    enabled: bool = False
    device_key: str = ""
    server: str = "https://api.day.app"

    @classmethod
    def from_dict(cls, data: dict) -> "BarkConfig":
        return cls(
            enabled=data.get("enabled", False),
            device_key=data.get("device_key", ""),
            server=data.get("server", "https://api.day.app")
        )


@dataclass
class MonitorConfig:
    """监控配置"""
    check_interval: int = 30
    headless: bool = True
    default_source: str = "feizhu"

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorConfig":
        return cls(
            check_interval=data.get("check_interval", 30),
            headless=data.get("headless", True),
            default_source=data.get("default_source", "feizhu")
        )


@dataclass
class NotificationsConfig:
    """通知配置"""
    email: EmailConfig
    webhook: WebhookConfig
    bark: BarkConfig

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationsConfig":
        return cls(
            email=EmailConfig.from_dict(data.get("email", {})),
            webhook=WebhookConfig.from_dict(data.get("webhook", {})),
            bark=BarkConfig.from_dict(data.get("bark", {}))
        )


@dataclass
class AppConfig:
    """应用完整配置"""
    monitor: MonitorConfig
    routes: List[Route]
    default_dates: DateConfig
    notifications: NotificationsConfig

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(
            monitor=MonitorConfig.from_dict(data.get("monitor", {})),
            routes=[Route.from_dict(r) for r in data.get("routes", [])],
            default_dates=DateConfig.from_dict(data.get("default_dates", {})),
            notifications=NotificationsConfig.from_dict(data.get("notifications", {}))
        )


def load_config(config_path: Union[str, Path]) -> AppConfig:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        AppConfig 实例

    Raises:
        ConfigError: 配置文件不存在或格式错误
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ConfigError("配置文件为空")

        config = AppConfig.from_dict(data)

        # 验证配置
        _validate_config(config)

        return config

    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件格式错误: {e}")
    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"加载配置失败: {e}")


def _validate_config(config: AppConfig) -> None:
    """验证配置有效性"""
    # 验证default_source
    valid_sources = {'ctrip', 'feizhu'}
    if config.monitor.default_source not in valid_sources:
        raise ConfigError(
            f"default_source must be one of {valid_sources}, "
            f"got: {config.monitor.default_source}"
        )

    if not config.routes:
        raise ConfigError("至少配置一条航线")

    for i, route in enumerate(config.routes):
        if not route.from_city or not route.to_city:
            raise ConfigError(f"航线 {i+1}: 出发地和目的地不能为空")

        if route.low_price_threshold <= 0:
            raise ConfigError(f"航线 {i+1}: 价格阈值必须大于0")

        if not route.dates.absolute_dates and not route.dates.relative_days:
            raise ConfigError(f"航线 {i+1}: 必须配置至少一个日期")

    # 检查至少启用了一个通知渠道
    has_notification = (
        config.notifications.email.enabled or
        config.notifications.webhook.enabled or
        config.notifications.bark.enabled
    )

    if not has_notification:
        raise ConfigError("至少启用一个通知渠道")


def get_airport_name(airport_code: str) -> str:
    """获取机场名称"""
    return AIRPORT_NAMES.get(airport_code, airport_code)
