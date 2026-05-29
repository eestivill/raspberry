"""Tests unitarios para la carga de configuración del monitor."""

import tempfile
from pathlib import Path

import pytest
import yaml

from monitor.config_loader import load_config
from monitor.models import MonitorConfig


class TestLoadConfig:
    """Tests para la función load_config."""

    def test_load_default_config(self):
        """Carga el config.yml por defecto y verifica valores esperados."""
        config = load_config()

        assert config.check_interval_seconds == 30
        assert config.health_check_timeout_seconds == 5
        assert config.max_consecutive_failures == 3
        assert config.max_restart_attempts == 3
        assert config.restart_window_minutes == 5
        assert config.memory_alert_threshold_percent == 85.0
        assert config.cpu_alert_threshold_percent == 90.0
        assert config.cpu_alert_consecutive_cycles == 3
        assert config.docker_reconnect_interval_seconds == 60
        assert config.docker_max_reconnect_attempts == 10
        assert config.disk_check_interval_seconds == 60
        assert config.disk_low_threshold_percent == 10.0
        assert config.disk_notification_cooldown_minutes == 10
        assert config.log_file == "../logs/health.log"
        assert config.log_max_size_mb == 10
        assert config.log_backup_count == 3

    def test_load_custom_config(self, tmp_path):
        """Carga un archivo de configuración personalizado."""
        custom_config = {
            "monitor": {
                "check_interval": 60,
                "health_check_timeout": 10,
                "max_failures": 5,
                "max_restarts": 2,
                "restart_window": 600,
            },
            "alerts": {
                "memory_threshold": 90,
                "cpu_threshold": 95,
                "cpu_consecutive_cycles": 5,
                "disk_low_threshold": 15,
            },
            "docker": {
                "reconnect_interval": 120,
                "max_reconnect_attempts": 5,
            },
            "disk": {
                "check_interval": 120,
                "notification_cooldown": 1200,
            },
            "logging": {
                "file": "/var/log/monitor.log",
                "max_size_mb": 20,
                "backup_count": 5,
            },
        }

        config_file = tmp_path / "config.yml"
        config_file.write_text(yaml.dump(custom_config))

        config = load_config(config_file)

        assert config.check_interval_seconds == 60
        assert config.health_check_timeout_seconds == 10
        assert config.max_consecutive_failures == 5
        assert config.max_restart_attempts == 2
        assert config.restart_window_minutes == 10
        assert config.memory_alert_threshold_percent == 90.0
        assert config.cpu_alert_threshold_percent == 95.0
        assert config.cpu_alert_consecutive_cycles == 5
        assert config.docker_reconnect_interval_seconds == 120
        assert config.docker_max_reconnect_attempts == 5
        assert config.disk_check_interval_seconds == 120
        assert config.disk_low_threshold_percent == 15.0
        assert config.disk_notification_cooldown_minutes == 20
        assert config.log_file == "/var/log/monitor.log"
        assert config.log_max_size_mb == 20
        assert config.log_backup_count == 5

    def test_load_partial_config_uses_defaults(self, tmp_path):
        """Campos faltantes usan valores por defecto."""
        partial_config = {
            "monitor": {
                "check_interval": 45,
            }
        }

        config_file = tmp_path / "config.yml"
        config_file.write_text(yaml.dump(partial_config))

        config = load_config(config_file)

        assert config.check_interval_seconds == 45
        # Los demás usan valores por defecto
        assert config.health_check_timeout_seconds == 5
        assert config.max_consecutive_failures == 3
        assert config.memory_alert_threshold_percent == 85.0
        assert config.cpu_alert_threshold_percent == 90.0

    def test_load_empty_config_uses_all_defaults(self, tmp_path):
        """Un archivo YAML vacío retorna todos los valores por defecto."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("")

        config = load_config(config_file)

        expected = MonitorConfig()
        assert config == expected

    def test_file_not_found_raises_error(self):
        """Archivo inexistente lanza FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="no encontrado"):
            load_config("/ruta/inexistente/config.yml")

    def test_invalid_yaml_raises_error(self, tmp_path):
        """YAML inválido lanza yaml.YAMLError."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(yaml.YAMLError):
            load_config(config_file)

    def test_returns_monitor_config_instance(self):
        """La función retorna una instancia de MonitorConfig."""
        config = load_config()
        assert isinstance(config, MonitorConfig)
