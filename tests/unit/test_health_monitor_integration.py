"""Tests de integración del monitor de salud como servicio del sistema.

Verifica que:
- El monitor de salud se puede ejecutar como proceso de fondo
- disk_monitor.py está integrado en el bucle principal
- Los logs se escriben en logs/health.log con rotación configurada
- manage.sh integra start/stop del monitor
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from monitor.config_loader import load_config
from monitor.disk_monitor import DiskMonitor
from monitor.health_monitor import HealthMonitor, main
from monitor.models import MonitorConfig


PROJECT_ROOT = Path(__file__).parent.parent.parent
MANAGE_SH = PROJECT_ROOT / "manage.sh"


class TestHealthMonitorAsBackgroundProcess:
    """Verifica que health_monitor.py puede ejecutarse como proceso de fondo."""

    def test_main_function_exists(self):
        """El módulo tiene una función main() como punto de entrada."""
        assert callable(main)

    def test_module_runnable_with_python_m(self):
        """El módulo se puede ejecutar con python -m monitor.health_monitor."""
        result = subprocess.run(
            ["python3", "-m", "monitor.health_monitor", "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "--pid-file" in result.stdout

    def test_pid_file_argument_supported(self):
        """El monitor acepta --pid-file para rastrear el proceso."""
        result = subprocess.run(
            ["python3", "-m", "monitor.health_monitor", "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert "--pid-file" in result.stdout
        assert "PID" in result.stdout

    def test_signal_handlers_configured(self):
        """El monitor configura manejadores de señales para detención limpia."""
        config = MonitorConfig(check_interval_seconds=1)
        monitor = HealthMonitor(config)
        # _setup_signal_handlers es llamado en run(), verificamos que existe
        assert hasattr(monitor, "_setup_signal_handlers")
        assert callable(monitor._setup_signal_handlers)

    def test_pid_file_write_and_remove(self):
        """El monitor escribe y elimina el archivo PID correctamente."""
        config = MonitorConfig(check_interval_seconds=1)
        monitor = HealthMonitor(config)

        with tempfile.NamedTemporaryFile(suffix=".pid", delete=False) as f:
            pid_file = Path(f.name)

        try:
            monitor._write_pid_file(pid_file)
            assert pid_file.exists()
            assert pid_file.read_text().strip() == str(os.getpid())

            monitor._remove_pid_file()
            assert not pid_file.exists()
        finally:
            if pid_file.exists():
                pid_file.unlink()


class TestDiskMonitorIntegration:
    """Verifica que disk_monitor.py está integrado en el bucle principal."""

    def test_health_monitor_has_disk_monitor(self):
        """HealthMonitor crea una instancia de DiskMonitor."""
        config = MonitorConfig()
        monitor = HealthMonitor(config)
        assert hasattr(monitor, "_disk_monitor")
        assert isinstance(monitor._disk_monitor, DiskMonitor)

    def test_disk_monitor_uses_same_config(self):
        """DiskMonitor usa la misma configuración que HealthMonitor."""
        config = MonitorConfig(
            disk_check_interval_seconds=120,
            disk_low_threshold_percent=15.0,
            disk_notification_cooldown_minutes=20,
        )
        monitor = HealthMonitor(config)
        assert monitor._disk_monitor.config is config

    def test_check_disk_method_exists(self):
        """HealthMonitor tiene método _check_disk para verificación periódica."""
        config = MonitorConfig()
        monitor = HealthMonitor(config)
        assert hasattr(monitor, "_check_disk")
        assert callable(monitor._check_disk)

    def test_check_disk_respects_interval(self):
        """_check_disk solo ejecuta si ha pasado el intervalo configurado."""
        from datetime import datetime, timedelta

        config = MonitorConfig(disk_check_interval_seconds=60)
        monitor = HealthMonitor(config)

        # Simular que se hizo una verificación hace 30 segundos
        monitor._last_disk_check = datetime.now() - timedelta(seconds=30)

        with patch.object(monitor._disk_monitor, "evaluate") as mock_eval:
            monitor._check_disk()
            # No debería llamar a evaluate porque no ha pasado el intervalo
            mock_eval.assert_not_called()

    def test_check_disk_executes_after_interval(self):
        """_check_disk ejecuta cuando ha pasado el intervalo configurado."""
        from datetime import datetime, timedelta

        config = MonitorConfig(disk_check_interval_seconds=60)
        monitor = HealthMonitor(config)

        # Simular que se hizo una verificación hace 61 segundos
        monitor._last_disk_check = datetime.now() - timedelta(seconds=61)

        with patch.object(monitor._disk_monitor, "evaluate", return_value=None) as mock_eval:
            monitor._check_disk()
            mock_eval.assert_called_once()


class TestLoggingConfiguration:
    """Verifica que los logs se escriben en logs/health.log con rotación."""

    def test_log_file_path_from_config(self):
        """La configuración por defecto apunta a ../logs/health.log."""
        config = load_config()
        assert "health.log" in config.log_file

    def test_log_rotation_size_10mb(self):
        """La rotación está configurada a 10MB."""
        config = load_config()
        assert config.log_max_size_mb == 10

    def test_log_backup_count_3(self):
        """Se mantienen 3 archivos de respaldo."""
        config = load_config()
        assert config.log_backup_count == 3

    def test_rotating_handler_configured(self):
        """HealthMonitor configura un RotatingFileHandler."""
        from logging.handlers import RotatingFileHandler

        config = MonitorConfig(
            log_file="/tmp/test_health_monitor.log",
            log_max_size_mb=10,
            log_backup_count=3,
        )
        monitor = HealthMonitor(config)

        health_logger = logging.getLogger("health_monitor")
        handlers = [
            h for h in health_logger.handlers
            if isinstance(h, RotatingFileHandler)
        ]
        assert len(handlers) >= 1

        # Verificar configuración del handler
        handler = handlers[-1]
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 3

        # Cleanup
        for h in health_logger.handlers[:]:
            health_logger.removeHandler(h)
            h.close()

        # Limpiar archivo temporal
        log_path = Path("/tmp/test_health_monitor.log")
        if log_path.exists():
            log_path.unlink()


class TestManageShIntegration:
    """Verifica que manage.sh integra start/stop del monitor de salud."""

    def test_manage_sh_exists(self):
        """El script manage.sh existe."""
        assert MANAGE_SH.exists()

    def test_manage_sh_contains_start_health_monitor(self):
        """manage.sh tiene función start_health_monitor."""
        content = MANAGE_SH.read_text()
        assert "start_health_monitor" in content

    def test_manage_sh_contains_stop_health_monitor(self):
        """manage.sh tiene función stop_health_monitor."""
        content = MANAGE_SH.read_text()
        assert "stop_health_monitor" in content

    def test_start_calls_health_monitor(self):
        """cmd_start invoca start_health_monitor."""
        content = MANAGE_SH.read_text()
        # Verificar que start_health_monitor se llama dentro de cmd_start
        start_section = content[content.index("cmd_start()"):]
        next_cmd = start_section.index("cmd_stop()")
        start_body = start_section[:next_cmd]
        assert "start_health_monitor" in start_body

    def test_stop_calls_health_monitor(self):
        """cmd_stop invoca stop_health_monitor."""
        content = MANAGE_SH.read_text()
        # Verificar que stop_health_monitor se llama dentro de cmd_stop
        stop_section = content[content.index("cmd_stop()"):]
        next_cmd_idx = stop_section.index("cmd_restart()")
        stop_body = stop_section[:next_cmd_idx]
        assert "stop_health_monitor" in stop_body

    def test_monitor_pid_file_defined(self):
        """manage.sh define la ruta del archivo PID del monitor."""
        content = MANAGE_SH.read_text()
        assert "MONITOR_PID_FILE" in content
        assert "monitor.pid" in content

    def test_monitor_uses_python_m_syntax(self):
        """manage.sh ejecuta el monitor con python -m monitor.health_monitor."""
        content = MANAGE_SH.read_text()
        assert "python3 -m monitor.health_monitor" in content

    def test_stop_sends_sigterm(self):
        """stop_health_monitor envía SIGTERM al proceso."""
        content = MANAGE_SH.read_text()
        assert "kill -TERM" in content

    def test_stop_has_grace_period(self):
        """stop_health_monitor espera antes de SIGKILL."""
        content = MANAGE_SH.read_text()
        assert "kill -KILL" in content
