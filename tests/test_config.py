"""
配置模块测试
"""

import pytest
from datetime import date
from pathlib import Path
import tempfile
import os

from src.config import (
    AppConfig,
    MonitorConfig,
    Route,
    DateConfig,
    EmailConfig,
    WebhookConfig,
    BarkConfig,
    NotificationsConfig,
    load_config,
)
from src.exceptions import ConfigError


class TestMonitorConfig:
    """测试MonitorConfig"""

    def test_from_dict_with_defaults(self):
        """测试使用默认值"""
        data = {}
        config = MonitorConfig.from_dict(data)
        assert config.check_interval == 30
        assert config.headless is True

    def test_from_dict_with_values(self):
        """测试使用指定值"""
        data = {
            "check_interval": 60,
            "headless": False
        }
        config = MonitorConfig.from_dict(data)
        assert config.check_interval == 60
        assert config.headless is False

    def test_default_source_default_value(self):
        """测试default_source默认值为feizhu"""
        # This test will pass once we add the field
        config = MonitorConfig()
        assert hasattr(config, "default_source")
        assert config.default_source == "feizhu"

    def test_default_source_valid_value(self):
        """测试设置有效的default_source值"""
        data = {
            "default_source": "ctrip"
        }
        config = MonitorConfig.from_dict(data)
        assert config.default_source == "ctrip"


class TestDateConfig:
    """测试DateConfig"""

    def test_from_dict_absolute_mode(self):
        """测试绝对日期模式"""
        data = {
            "mode": "absolute",
            "absolute_dates": ["2024-01-01", "2024-01-02"]
        }
        config = DateConfig.from_dict(data)
        assert config.mode == "absolute"
        assert config.absolute_dates == [date(2024, 1, 1), date(2024, 1, 2)]

    def test_from_dict_relative_mode(self):
        """测试相对日期模式"""
        data = {
            "mode": "relative",
            "relative_days": [1, 2, 3]
        }
        config = DateConfig.from_dict(data)
        assert config.mode == "relative"
        assert config.relative_days == [1, 2, 3]


class TestRoute:
    """测试Route"""

    def test_from_dict(self):
        """测试从字典创建Route"""
        data = {
            "from": "北京",
            "to": "上海",
            "low_price_threshold": 500,
            "dates": {
                "mode": "absolute",
                "absolute_dates": ["2024-01-01"]
            }
        }
        route = Route.from_dict(data)
        assert route.from_city == "北京"
        assert route.to_city == "上海"
        assert route.low_price_threshold == 500


class TestNotificationsConfig:
    """测试NotificationsConfig"""

    def test_from_dict(self):
        """测试从字典创建NotificationsConfig"""
        data = {
            "email": {
                "enabled": True,
                "smtp_server": "smtp.example.com",
                "smtp_port": 465,
                "username": "test@example.com",
                "password": "password",
                "to": ["user@example.com"]
            },
            "webhook": {"enabled": False},
            "bark": {"enabled": False}
        }
        config = NotificationsConfig.from_dict(data)
        assert config.email.enabled is True
        assert config.email.smtp_server == "smtp.example.com"


class TestLoadConfig:
    """测试load_config函数"""

    def test_load_valid_config(self):
        """测试加载有效的配置文件"""
        config_data = """
monitor:
  check_interval: 30
  headless: true
  default_source: feizhu

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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.monitor.check_interval == 30
            assert config.monitor.headless is True
            assert config.monitor.default_source == "feizhu"
            assert len(config.routes) == 1
            assert config.routes[0].from_city == "北京"
            assert config.notifications.email.enabled is True
        finally:
            os.unlink(temp_path)

    def test_load_config_with_ctrip_source(self):
        """测试加载配置时指定ctrip作为默认数据源"""
        config_data = """
monitor:
  check_interval: 30
  headless: true
  default_source: ctrip

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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.monitor.default_source == "ctrip"
        finally:
            os.unlink(temp_path)

    def test_load_config_missing_file(self):
        """测试加载不存在的配置文件"""
        with pytest.raises(ConfigError) as exc_info:
            load_config("/nonexistent/path/config.yaml")
        assert "配置文件不存在" in str(exc_info.value)

    def test_load_config_no_default_source_uses_feizhu(self):
        """测试配置文件中未指定default_source时使用默认值feizhu"""
        config_data = """
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.monitor.default_source == "feizhu"
        finally:
            os.unlink(temp_path)


class TestConfigValidation:
    """测试配置验证"""

    def test_validate_invalid_default_source(self):
        """测试验证无效的default_source值"""
        config_data = """
monitor:
  check_interval: 30
  headless: true
  default_source: invalid_source

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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(temp_path)
            assert "default_source" in str(exc_info.value)
            assert "ctrip" in str(exc_info.value)
            assert "feizhu" in str(exc_info.value)
        finally:
            os.unlink(temp_path)

    def test_validate_no_routes(self):
        """测试验证没有配置航线"""
        config_data = """
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(temp_path)
            assert "至少配置一条航线" in str(exc_info.value)
        finally:
            os.unlink(temp_path)

    def test_validate_invalid_route_threshold(self):
        """测试验证航线价格阈值小于等于0"""
        config_data = """
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(temp_path)
            assert "价格阈值必须大于0" in str(exc_info.value)
        finally:
            os.unlink(temp_path)

    def test_validate_no_notification(self):
        """测试验证没有启用任何通知渠道"""
        config_data = """
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(config_data)
            temp_path = f.name

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(temp_path)
            assert "至少启用一个通知渠道" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
