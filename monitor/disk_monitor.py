"""Monitor de espacio en disco para la infraestructura Docker.

Verifica periódicamente el espacio disponible en la ruta de volúmenes
y genera alertas cuando el espacio libre es inferior al umbral configurado.
"""

import logging
import shutil
from datetime import datetime, timedelta
from typing import Optional

from monitor.models import Alert, DiskStatus, MonitorConfig


logger = logging.getLogger(__name__)


class DiskMonitor:
    """Monitor de espacio en disco.

    Verifica el espacio disponible en la ruta de volúmenes y genera
    alertas cuando el espacio libre cae por debajo del umbral configurado.
    Respeta un cooldown entre notificaciones para evitar spam de alertas.
    """

    def __init__(self, config: MonitorConfig):
        """Inicializa el monitor de disco.

        Args:
            config: Configuración del monitor con umbrales y tiempos.
        """
        self.config = config
        self._last_notification_time: Optional[datetime] = None

    @property
    def check_interval_seconds(self) -> int:
        """Intervalo entre verificaciones de disco en segundos."""
        return self.config.disk_check_interval_seconds

    @property
    def low_threshold_percent(self) -> float:
        """Umbral de espacio bajo en porcentaje."""
        return self.config.disk_low_threshold_percent

    @property
    def notification_cooldown_minutes(self) -> int:
        """Tiempo mínimo entre notificaciones en minutos."""
        return self.config.disk_notification_cooldown_minutes

    def check_disk_space(self, volume_path: str) -> DiskStatus:
        """Verifica el espacio disponible en la ruta de volúmenes.

        Usa shutil.disk_usage para obtener las estadísticas del sistema
        de archivos donde reside la ruta indicada.

        Args:
            volume_path: Ruta del directorio de volúmenes a verificar.

        Returns:
            DiskStatus con la información de espacio en disco.

        Raises:
            OSError: Si la ruta no existe o no es accesible.
        """
        usage = shutil.disk_usage(volume_path)

        total_mb = usage.total / (1024 * 1024)
        used_mb = usage.used / (1024 * 1024)
        available_mb = usage.free / (1024 * 1024)
        usage_percent = (usage.used / usage.total) * 100 if usage.total > 0 else 0.0

        available_percent = (usage.free / usage.total) * 100 if usage.total > 0 else 0.0
        is_low = available_percent < self.low_threshold_percent

        return DiskStatus(
            path=volume_path,
            total_mb=total_mb,
            used_mb=used_mb,
            available_mb=available_mb,
            usage_percent=usage_percent,
            is_low=is_low,
        )

    def should_notify(self, last_notification_time: Optional[datetime] = None) -> bool:
        """Determina si debe emitir una notificación.

        Permite como máximo una notificación cada N minutos (configurado
        en disk_notification_cooldown_minutes). Si no se ha enviado
        ninguna notificación previamente, siempre retorna True.

        Args:
            last_notification_time: Marca de tiempo de la última notificación.
                Si es None, usa el tiempo interno rastreado por esta instancia.

        Returns:
            True si ha pasado suficiente tiempo desde la última notificación.
        """
        effective_last = last_notification_time or self._last_notification_time

        if effective_last is None:
            return True

        cooldown = timedelta(minutes=self.notification_cooldown_minutes)
        now = datetime.now()
        return (now - effective_last) >= cooldown

    def evaluate(self, volume_path: str) -> Optional[Alert]:
        """Evalúa el estado del disco y genera una alerta si corresponde.

        Combina check_disk_space y should_notify para determinar si se
        debe generar una alerta de espacio bajo en disco.

        Args:
            volume_path: Ruta del directorio de volúmenes a verificar.

        Returns:
            Alert si el espacio es bajo y el cooldown lo permite, None en caso contrario.
        """
        try:
            status = self.check_disk_space(volume_path)
        except OSError as e:
            logger.error("Error al verificar espacio en disco en %s: %s", volume_path, e)
            return None

        if not status.is_low:
            return None

        if not self.should_notify():
            logger.debug(
                "Espacio bajo en %s pero cooldown activo, omitiendo notificación",
                volume_path,
            )
            return None

        self._last_notification_time = datetime.now()

        available_percent = 100.0 - status.usage_percent
        alert = Alert(
            level="warning",
            container_name="system",
            message=(
                f"Espacio en disco bajo en {volume_path}: "
                f"{status.available_mb:.1f} MB disponibles "
                f"({available_percent:.1f}% libre)"
            ),
            timestamp=datetime.now(),
            metric_value=available_percent,
            threshold=self.low_threshold_percent,
        )

        logger.warning(alert.message)
        return alert
