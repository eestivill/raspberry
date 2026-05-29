"""Tests unitarios para el monitor de disco."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from monitor.disk_monitor import DiskMonitor
from monitor.models import MonitorConfig


@pytest.fixture
def config():
    """Configuración por defecto para tests."""
    return MonitorConfig(
        disk_check_interval_seconds=60,
        disk_low_threshold_percent=10.0,
        disk_notification_cooldown_minutes=10,
    )


@pytest.fixture
def monitor(config):
    """Instancia de DiskMonitor con configuración por defecto."""
    return DiskMonitor(config)


class TestCheckDiskSpace:
    """Tests para check_disk_space."""

    def test_returns_disk_status_for_valid_path(self, monitor, tmp_path):
        """Verifica que retorna DiskStatus para una ruta válida."""
        status = monitor.check_disk_space(str(tmp_path))

        assert status.path == str(tmp_path)
        assert status.total_mb > 0
        assert status.available_mb >= 0
        assert status.used_mb >= 0
        assert 0 <= status.usage_percent <= 100

    def test_raises_oserror_for_invalid_path(self, monitor):
        """Verifica que lanza OSError para una ruta inexistente."""
        with pytest.raises(OSError):
            monitor.check_disk_space("/ruta/inexistente/xyz123")

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_is_low_true_when_below_threshold(self, mock_usage, monitor):
        """Verifica que is_low es True cuando el espacio libre < 10%."""
        # Simular disco de 100GB con solo 5GB libres (5%)
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 95 * 1024**3,
            "free": 5 * 1024**3,
        })()

        status = monitor.check_disk_space("/volumes")

        assert status.is_low is True
        assert status.available_mb == pytest.approx(5 * 1024, rel=0.01)

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_is_low_false_when_above_threshold(self, mock_usage, monitor):
        """Verifica que is_low es False cuando el espacio libre >= 10%."""
        # Simular disco de 100GB con 20GB libres (20%)
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 80 * 1024**3,
            "free": 20 * 1024**3,
        })()

        status = monitor.check_disk_space("/volumes")

        assert status.is_low is False

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_is_low_boundary_at_exactly_10_percent(self, mock_usage, monitor):
        """Verifica el comportamiento en el límite exacto del 10%."""
        # Exactamente 10% libre - no debería ser "low" (< 10% es low)
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 90 * 1024**3,
            "free": 10 * 1024**3,
        })()

        status = monitor.check_disk_space("/volumes")

        assert status.is_low is False


class TestShouldNotify:
    """Tests para should_notify."""

    def test_first_notification_always_allowed(self, monitor):
        """La primera notificación siempre se permite."""
        assert monitor.should_notify() is True

    def test_notification_blocked_within_cooldown(self, monitor):
        """Notificación bloqueada si no ha pasado el cooldown."""
        recent_time = datetime.now() - timedelta(minutes=5)
        assert monitor.should_notify(recent_time) is False

    def test_notification_allowed_after_cooldown(self, monitor):
        """Notificación permitida después del cooldown."""
        old_time = datetime.now() - timedelta(minutes=11)
        assert monitor.should_notify(old_time) is True

    def test_notification_at_exact_cooldown_boundary(self, monitor):
        """Notificación permitida exactamente al cumplir el cooldown."""
        boundary_time = datetime.now() - timedelta(minutes=10)
        assert monitor.should_notify(boundary_time) is True

    def test_uses_internal_state_when_no_arg(self, monitor):
        """Usa el estado interno cuando no se pasa argumento."""
        # Sin notificación previa, debería permitir
        assert monitor.should_notify() is True

        # Simular que se envió una notificación hace 5 minutos
        monitor._last_notification_time = datetime.now() - timedelta(minutes=5)
        assert monitor.should_notify() is False

        # Simular que se envió hace 11 minutos
        monitor._last_notification_time = datetime.now() - timedelta(minutes=11)
        assert monitor.should_notify() is True


class TestEvaluate:
    """Tests para evaluate (integración de check + notify)."""

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_generates_alert_when_disk_low(self, mock_usage, monitor):
        """Genera alerta cuando el espacio es bajo y cooldown lo permite."""
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 95 * 1024**3,
            "free": 5 * 1024**3,
        })()

        alert = monitor.evaluate("/volumes")

        assert alert is not None
        assert alert.level == "warning"
        assert alert.container_name == "system"
        assert "/volumes" in alert.message
        assert alert.threshold == 10.0

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_no_alert_when_disk_ok(self, mock_usage, monitor):
        """No genera alerta cuando hay suficiente espacio."""
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 50 * 1024**3,
            "free": 50 * 1024**3,
        })()

        alert = monitor.evaluate("/volumes")

        assert alert is None

    @patch("monitor.disk_monitor.shutil.disk_usage")
    def test_no_alert_during_cooldown(self, mock_usage, monitor):
        """No genera alerta si el cooldown está activo."""
        mock_usage.return_value = type("Usage", (), {
            "total": 100 * 1024**3,
            "used": 95 * 1024**3,
            "free": 5 * 1024**3,
        })()

        # Primera alerta se genera
        alert1 = monitor.evaluate("/volumes")
        assert alert1 is not None

        # Segunda alerta bloqueada por cooldown
        alert2 = monitor.evaluate("/volumes")
        assert alert2 is None

    def test_no_alert_on_invalid_path(self, monitor):
        """No genera alerta si la ruta es inválida (registra error)."""
        alert = monitor.evaluate("/ruta/inexistente/xyz123")
        assert alert is None


class TestConfiguration:
    """Tests para verificar que la configuración se aplica correctamente."""

    def test_custom_threshold(self):
        """Verifica que se respeta un umbral personalizado."""
        config = MonitorConfig(disk_low_threshold_percent=20.0)
        monitor = DiskMonitor(config)
        assert monitor.low_threshold_percent == 20.0

    def test_custom_cooldown(self):
        """Verifica que se respeta un cooldown personalizado."""
        config = MonitorConfig(disk_notification_cooldown_minutes=30)
        monitor = DiskMonitor(config)
        assert monitor.notification_cooldown_minutes == 30

    def test_check_interval(self):
        """Verifica que se expone el intervalo de verificación."""
        config = MonitorConfig(disk_check_interval_seconds=120)
        monitor = DiskMonitor(config)
        assert monitor.check_interval_seconds == 120
