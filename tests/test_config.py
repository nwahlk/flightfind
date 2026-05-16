"""Tests for configuration loading and validation."""

from datetime import date
import os
import tempfile

import pytest

from src.config import AIRPORT_NAMES, DateConfig, FlyAIConfig, MonitorConfig, NotificationsConfig, Route, get_airport_name, load_config
from src.exceptions import ConfigError


class TestMonitorConfig:
    def test_from_dict_with_defaults(self):
        config = MonitorConfig.from_dict({})
        assert config.check_interval == 30
        assert config.headless is True
        assert config.sources == ["flyai"]
        assert config.default_source == "flyai"

    def test_from_dict_with_values(self):
        config = MonitorConfig.from_dict(
            {
                "check_interval": 60,
                "headless": False,
                "sources": ["flyai", "flyai_train"],
            }
        )
        assert config.check_interval == 60
        assert config.headless is False
        assert config.sources == ["flyai", "flyai_train"]
        assert config.default_source == "flyai"

    def test_source_aliases(self):
        config = MonitorConfig.from_dict({"sources": ["feizhu", "train"]})
        assert config.sources == ["flyai", "flyai_train"]

    def test_spring_source_supported(self):
        config = MonitorConfig.from_dict({"sources": ["flyai", "spring"]})
        assert config.sources == ["flyai", "spring"]


class TestDateConfig:
    def test_from_dict_absolute_mode(self):
        config = DateConfig.from_dict(
            {
                "mode": "absolute",
                "absolute_dates": ["2024-01-01", "2024-01-02"],
            }
        )
        assert config.mode == "absolute"
        assert config.absolute_dates == [date(2024, 1, 1), date(2024, 1, 2)]

    def test_from_dict_relative_mode(self):
        config = DateConfig.from_dict(
            {
                "mode": "relative",
                "relative_days": [1, 2, 3],
            }
        )
        assert config.mode == "relative"
        assert config.relative_days == [1, 2, 3]

    def test_resolved_dates_relative_mode(self):
        config = DateConfig(mode="relative", relative_days=[1, 3])
        assert config.resolved_dates(base_date=date(2026, 5, 16)) == [
            date(2026, 5, 17),
            date(2026, 5, 19),
        ]


class TestRoute:
    def test_from_dict(self):
        route = Route.from_dict(
            {
                "from": "北京",
                "to": "上海",
                "low_price_threshold": 500,
                "dates": {
                    "mode": "absolute",
                    "absolute_dates": ["2024-01-01"],
                },
            }
        )
        assert route.from_city == "北京"
        assert route.to_city == "上海"
        assert route.low_price_threshold == 500


class TestNotificationsConfig:
    def test_from_dict(self):
        config = NotificationsConfig.from_dict(
            {
                "email": {
                    "enabled": True,
                    "smtp_server": "smtp.example.com",
                    "smtp_port": 465,
                    "username": "test@example.com",
                    "password": "password",
                    "to": ["user@example.com"],
                },
                "webhook": {"enabled": False},
                "bark": {"enabled": False},
            }
        )
        assert config.email.enabled is True
        assert config.email.smtp_server == "smtp.example.com"


class TestFlyAIConfig:
    def test_from_dict_with_defaults(self):
        config = FlyAIConfig.from_dict({})
        assert config.api_key == ""
        assert config.sign_secret == ""
        assert config.enabled is False

    def test_from_dict_with_values(self):
        config = FlyAIConfig.from_dict(
            {"api_key": "sk-test", "sign_secret": "secret-test"}
        )
        assert config.api_key == "sk-test"
        assert config.sign_secret == "secret-test"
        assert config.enabled is True


def _write_temp_config(config_data: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        handle.write(config_data)
        return handle.name


class TestLoadConfig:
    def test_load_valid_config(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true
  sources: [feizhu]

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            config = load_config(temp_path)
            assert config.monitor.check_interval == 30
            assert config.monitor.headless is True
            assert config.monitor.sources == ["flyai"]
            assert config.monitor.default_source == "flyai"
            assert len(config.routes) == 1
            assert config.routes[0].from_city == "北京"
            assert config.notifications.email.enabled is True
        finally:
            os.unlink(temp_path)

    def test_load_config_with_flyai_train_source(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true
  sources: [flyai_train]

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            config = load_config(temp_path)
            assert config.monitor.sources == ["flyai_train"]
            assert config.monitor.default_source == "flyai_train"
        finally:
            os.unlink(temp_path)

    def test_load_config_missing_file(self):
        with pytest.raises(ConfigError, match="Config file not found"):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_no_source_uses_flyai(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            config = load_config(temp_path)
            assert config.monitor.sources == ["flyai"]
            assert config.monitor.default_source == "flyai"
        finally:
            os.unlink(temp_path)

    def test_route_uses_default_dates_when_dates_omitted(self):
        temp_path = _write_temp_config(
            """
monitor:
  sources: [flyai]

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500

default_dates:
  mode: absolute
  absolute_dates:
    - "2026-05-20"

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    username: test@example.com
    password: password
    to:
      - user@example.com
"""
        )
        try:
            config = load_config(temp_path)
            assert config.routes[0].dates.absolute_dates == [date(2026, 5, 20)]
        finally:
            os.unlink(temp_path)


class TestConfigValidation:
    def test_validate_invalid_default_source(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true
  sources: [invalid_source]

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(temp_path)
            message = str(exc_info.value)
            assert "sources must be one of" in message
            assert "flyai" in message
            assert "flyai_train" in message
            assert "spring" in message
        finally:
            os.unlink(temp_path)

    def test_validate_no_routes(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true

routes: []

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            with pytest.raises(ConfigError, match="At least one route must be configured"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_invalid_route_threshold(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true

routes:
  - from: 北京
    to: 上海
    low_price_threshold: -100
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: true
    smtp_server: smtp.example.com
    smtp_port: 465
    username: test@example.com
    password: password
    to:
      - user@example.com
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            with pytest.raises(ConfigError, match="low_price_threshold must be greater than 0"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_no_notification(self):
        temp_path = _write_temp_config(
            """
monitor:
  check_interval: 30
  headless: true

routes:
  - from: 北京
    to: 上海
    low_price_threshold: 500
    dates:
      mode: absolute
      absolute_dates:
        - "2024-01-01"

default_dates:
  mode: relative
  relative_days: [1, 2, 3]

notifications:
  email:
    enabled: false
  webhook:
    enabled: false
  bark:
    enabled: false
"""
        )
        try:
            with pytest.raises(ConfigError, match="At least one notification channel must be enabled"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)


class TestAirportNames:
    def test_get_airport_name_known_code(self):
        assert get_airport_name("PEK") == "Beijing Capital"
        assert get_airport_name("PVG") == "Shanghai Pudong"
        assert get_airport_name("CAN") == "Guangzhou Baiyun"

    def test_get_airport_name_unknown_code(self):
        assert get_airport_name("XYZ") == "XYZ"

    def test_get_airport_name_empty_string(self):
        assert get_airport_name("") == ""

    def test_airport_names_constant(self):
        assert "PEK" in AIRPORT_NAMES
        assert "PVG" in AIRPORT_NAMES
        assert "CAN" in AIRPORT_NAMES
        assert AIRPORT_NAMES["PEK"] == "Beijing Capital"
        assert AIRPORT_NAMES["PVG"] == "Shanghai Pudong"
        assert AIRPORT_NAMES["CAN"] == "Guangzhou Baiyun"
