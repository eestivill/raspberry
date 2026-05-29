"""Monitor de salud para contenedores Docker.

Verifica periódicamente el estado de los contenedores, recopila métricas
de recursos (CPU, memoria, red), genera alertas cuando se superan umbrales
configurados, y gestiona reinicios automáticos de contenedores no saludables.

Implementa una máquina de estados por contenedor:
    Healthy → CheckFailed → Unhealthy → Restarting → Critical
"""

import logging
import os
import signal
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import docker
from docker.errors import APIError, DockerException, NotFound

from monitor.config_loader import load_config
from monitor.disk_monitor import DiskMonitor
from monitor.models import (
    Alert,
    ContainerState,
    HealthStatus,
    MonitorConfig,
    ResourceMetrics,
    RestartResult,
)


logger = logging.getLogger("health_monitor")


class HealthMonitor:
    """Monitor de salud de contenedores Docker.

    Verifica el estado de cada contenedor activo en intervalos configurables,
    recopila métricas de recursos, evalúa alertas por umbrales y gestiona
    reinicios automáticos con máquina de estados.
    """

    def __init__(self, config: Optional[MonitorConfig] = None):
        """Inicializa el monitor con la configuración dada.

        Args:
            config: Configuración del monitor. Si es None, se carga
                    desde el archivo config.yml por defecto.
        """
        self.config = config or load_config()
        self._setup_logging()

        # Estado de cada contenedor: container_id -> HealthStatus
        self._container_states: dict[str, HealthStatus] = {}

        # Historial de CPU por contenedor para detectar ciclos consecutivos
        self._cpu_history: dict[str, list[float]] = {}

        # Historial de reintentos: container_id -> list[datetime]
        self._restart_history: dict[str, list[datetime]] = {}

        # Estado de conexión a Docker
        self._docker_client: Optional[docker.DockerClient] = None
        self._docker_connected: bool = False
        self._reconnect_attempts: int = 0
        self._disconnected_since: Optional[datetime] = None

        # Monitor de disco integrado
        self._disk_monitor = DiskMonitor(self.config)
        self._last_disk_check: Optional[datetime] = None

        # Ruta de volúmenes para verificación de disco
        self._volumes_path = os.environ.get(
            "VOLUMES_PATH",
            str(Path(__file__).parent.parent / "volumes"),
        )

        # Control de proceso
        self._running: bool = False
        self._pid_file: Optional[Path] = None

    def _setup_logging(self) -> None:
        """Configura logging con rotación de archivos."""
        log_path = Path(self.config.log_file)
        if not log_path.is_absolute():
            log_path = Path(__file__).parent / log_path

        log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=self.config.log_max_size_mb * 1024 * 1024,
            backupCount=self.config.log_backup_count,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "[%(levelname)-5s] %(asctime)s - %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # También log a consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    def _write_pid_file(self, pid_file: Path) -> None:
        """Escribe el PID del proceso actual en un archivo.

        Args:
            pid_file: Ruta al archivo PID.
        """
        self._pid_file = pid_file
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
        logger.info("PID %d escrito en %s", os.getpid(), pid_file)

    def _remove_pid_file(self) -> None:
        """Elimina el archivo PID si existe."""
        if self._pid_file and self._pid_file.exists():
            self._pid_file.unlink()
            logger.info("Archivo PID eliminado: %s", self._pid_file)

    def _setup_signal_handlers(self) -> None:
        """Configura manejadores de señales para detención limpia."""
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame) -> None:
        """Maneja señales de terminación para detención limpia.

        Args:
            signum: Número de señal recibida.
            frame: Frame de ejecución actual.
        """
        sig_name = signal.Signals(signum).name
        logger.info("Señal %s recibida. Deteniendo monitor de salud...", sig_name)
        self._running = False

    def _check_disk(self) -> None:
        """Ejecuta la verificación de disco si ha pasado el intervalo configurado."""
        now = datetime.now()

        if self._last_disk_check is not None:
            elapsed = (now - self._last_disk_check).total_seconds()
            if elapsed < self.config.disk_check_interval_seconds:
                return

        self._last_disk_check = now

        alert = self._disk_monitor.evaluate(self._volumes_path)
        if alert:
            self._emit_alert(alert)

    def _connect_docker(self) -> bool:
        """Intenta conectar al Docker Engine.

        Returns:
            True si la conexión fue exitosa, False en caso contrario.
        """
        try:
            self._docker_client = docker.from_env(timeout=self.config.health_check_timeout_seconds)
            self._docker_client.ping()
            self._docker_connected = True
            self._reconnect_attempts = 0
            self._disconnected_since = None
            logger.info("Conexión a Docker Engine establecida")
            return True
        except DockerException as e:
            logger.error("No se pudo conectar a Docker Engine: %s", e)
            self._docker_connected = False
            if self._disconnected_since is None:
                self._disconnected_since = datetime.now()
            return False

    def _handle_docker_disconnection(self) -> bool:
        """Gestiona la desconexión de Docker Engine.

        Reintenta la conexión cada docker_reconnect_interval_seconds hasta
        un máximo de docker_max_reconnect_attempts intentos.

        Returns:
            True si se reconectó exitosamente, False si se agotaron los intentos.
        """
        self._reconnect_attempts += 1
        logger.warning(
            "Intento de reconexión %d/%d a Docker Engine",
            self._reconnect_attempts,
            self.config.docker_max_reconnect_attempts,
        )

        if self._connect_docker():
            logger.info(
                "Reconexión exitosa después de %d intentos",
                self._reconnect_attempts,
            )
            return True

        if self._reconnect_attempts >= self.config.docker_max_reconnect_attempts:
            duration = datetime.now() - self._disconnected_since if self._disconnected_since else timedelta(0)
            alert = Alert(
                level="critical",
                container_name="docker_engine",
                message=(
                    f"Pérdida de conexión a Docker Engine. "
                    f"Agotados {self.config.docker_max_reconnect_attempts} intentos de reconexión. "
                    f"Duración de la desconexión: {duration}"
                ),
                timestamp=datetime.now(),
            )
            self._emit_alert(alert)
            logger.critical(
                "Agotados los intentos de reconexión a Docker Engine. "
                "Duración de desconexión: %s",
                duration,
            )
            return False

        return False

    def check_container_health(self, container_id: str) -> HealthStatus:
        """Verifica la salud de un contenedor específico.

        Comprueba que el contenedor está en ejecución y responde dentro
        del timeout configurado (5s por defecto).

        Args:
            container_id: ID del contenedor a verificar.

        Returns:
            HealthStatus con el estado actual del contenedor.
        """
        now = datetime.now()

        # Obtener o crear estado previo
        prev_status = self._container_states.get(container_id)

        try:
            container = self._docker_client.containers.get(container_id)
            container.reload()

            container_name = container.name
            is_running = container.status == "running"

            # Verificar health check de Docker si está configurado
            health = container.attrs.get("State", {}).get("Health", {})
            docker_health_status = health.get("Status", "none")

            if is_running and docker_health_status in ("healthy", "none"):
                # Contenedor saludable
                new_state = ContainerState.HEALTHY
                consecutive_failures = 0
            else:
                # Contenedor no responde o no está saludable
                consecutive_failures = (
                    prev_status.consecutive_failures + 1 if prev_status else 1
                )
                if consecutive_failures >= self.config.max_consecutive_failures:
                    new_state = ContainerState.UNHEALTHY
                else:
                    new_state = ContainerState.CHECK_FAILED

        except NotFound:
            container_name = prev_status.container_name if prev_status else container_id
            consecutive_failures = (
                prev_status.consecutive_failures + 1 if prev_status else 1
            )
            if consecutive_failures >= self.config.max_consecutive_failures:
                new_state = ContainerState.UNHEALTHY
            else:
                new_state = ContainerState.CHECK_FAILED

        except APIError as e:
            logger.error(
                "Error de API Docker al verificar contenedor %s: %s",
                container_id, e,
            )
            container_name = prev_status.container_name if prev_status else container_id
            consecutive_failures = (
                prev_status.consecutive_failures + 1 if prev_status else 1
            )
            if consecutive_failures >= self.config.max_consecutive_failures:
                new_state = ContainerState.UNHEALTHY
            else:
                new_state = ContainerState.CHECK_FAILED

        # Determinar si hubo cambio de estado
        prev_state = prev_status.state if prev_status else None
        last_state_change = now if prev_state != new_state else (
            prev_status.last_state_change if prev_status else now
        )

        restart_attempts = prev_status.restart_attempts if prev_status else 0

        status = HealthStatus(
            container_id=container_id,
            container_name=container_name,
            state=new_state,
            consecutive_failures=consecutive_failures,
            restart_attempts=restart_attempts,
            last_check=now,
            last_state_change=last_state_change,
        )

        self._container_states[container_id] = status

        if new_state == ContainerState.UNHEALTHY and prev_state != ContainerState.UNHEALTHY:
            logger.warning(
                "Contenedor %s marcado como no saludable después de %d fallos consecutivos",
                container_name,
                consecutive_failures,
            )

        return status

    def check_resource_usage(self, container_id: str) -> ResourceMetrics:
        """Obtiene métricas de uso de recursos de un contenedor.

        Recopila CPU, memoria y red del contenedor especificado.

        Args:
            container_id: ID del contenedor.

        Returns:
            ResourceMetrics con las métricas actuales.

        Raises:
            DockerException: Si no se pueden obtener las estadísticas.
        """
        container = self._docker_client.containers.get(container_id)
        stats = container.stats(stream=False)

        # Calcular uso de CPU
        cpu_percent = self._calculate_cpu_percent(stats)

        # Calcular uso de memoria
        memory_stats = stats.get("memory_stats", {})
        memory_usage = memory_stats.get("usage", 0)
        memory_limit = memory_stats.get("limit", 1)
        memory_usage_mb = memory_usage / (1024 * 1024)
        memory_limit_mb = memory_limit / (1024 * 1024)
        memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0.0

        # Calcular uso de red
        networks = stats.get("networks", {})
        network_rx = sum(net.get("rx_bytes", 0) for net in networks.values())
        network_tx = sum(net.get("tx_bytes", 0) for net in networks.values())

        return ResourceMetrics(
            container_name=container.name,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_usage_mb=memory_usage_mb,
            memory_limit_mb=memory_limit_mb,
            network_rx_bytes=network_rx,
            network_tx_bytes=network_tx,
            timestamp=datetime.now(),
        )

    def _calculate_cpu_percent(self, stats: dict) -> float:
        """Calcula el porcentaje de uso de CPU a partir de las estadísticas Docker.

        Args:
            stats: Diccionario de estadísticas del contenedor.

        Returns:
            Porcentaje de uso de CPU.
        """
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_usage = cpu_stats.get("cpu_usage", {})
        precpu_usage = precpu_stats.get("cpu_usage", {})

        cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)

        online_cpus = cpu_stats.get("online_cpus", 1)

        if system_delta > 0 and cpu_delta >= 0:
            return (cpu_delta / system_delta) * online_cpus * 100.0
        return 0.0

    def evaluate_alerts(self, metrics: ResourceMetrics, container_name: str) -> list[Alert]:
        """Evalúa si las métricas superan los umbrales configurados.

        Genera alertas para:
        - Memoria > 85% del límite asignado
        - CPU > 90% durante 3 ciclos consecutivos

        Args:
            metrics: Métricas de recursos del contenedor.
            container_name: Nombre del contenedor.

        Returns:
            Lista de alertas generadas (puede estar vacía).
        """
        alerts: list[Alert] = []
        now = datetime.now()

        # Evaluar umbral de memoria
        if metrics.memory_percent > self.config.memory_alert_threshold_percent:
            alert = Alert(
                level="warning",
                container_name=container_name,
                message=(
                    f"Uso de memoria elevado: {metrics.memory_percent:.1f}% "
                    f"(umbral: {self.config.memory_alert_threshold_percent}%)"
                ),
                timestamp=now,
                metric_value=metrics.memory_percent,
                threshold=self.config.memory_alert_threshold_percent,
            )
            alerts.append(alert)
            logger.warning(
                "Alerta de memoria para %s: %.1f%% (umbral: %.1f%%)",
                container_name,
                metrics.memory_percent,
                self.config.memory_alert_threshold_percent,
            )

        # Evaluar umbral de CPU (requiere ciclos consecutivos)
        if container_name not in self._cpu_history:
            self._cpu_history[container_name] = []

        self._cpu_history[container_name].append(metrics.cpu_percent)

        # Mantener solo los últimos N ciclos necesarios
        max_history = self.config.cpu_alert_consecutive_cycles
        if len(self._cpu_history[container_name]) > max_history:
            self._cpu_history[container_name] = self._cpu_history[container_name][-max_history:]

        # Verificar si los últimos N ciclos superan el umbral
        cpu_readings = self._cpu_history[container_name]
        if len(cpu_readings) >= self.config.cpu_alert_consecutive_cycles:
            recent = cpu_readings[-self.config.cpu_alert_consecutive_cycles:]
            if all(cpu > self.config.cpu_alert_threshold_percent for cpu in recent):
                avg_cpu = sum(recent) / len(recent)
                alert = Alert(
                    level="warning",
                    container_name=container_name,
                    message=(
                        f"Uso de CPU elevado sostenido: {avg_cpu:.1f}% promedio "
                        f"durante {self.config.cpu_alert_consecutive_cycles} ciclos consecutivos "
                        f"(umbral: {self.config.cpu_alert_threshold_percent}%)"
                    ),
                    timestamp=now,
                    metric_value=avg_cpu,
                    threshold=self.config.cpu_alert_threshold_percent,
                )
                alerts.append(alert)
                logger.warning(
                    "Alerta de CPU para %s: %.1f%% promedio en %d ciclos (umbral: %.1f%%)",
                    container_name,
                    avg_cpu,
                    self.config.cpu_alert_consecutive_cycles,
                    self.config.cpu_alert_threshold_percent,
                )
                # Resetear historial después de generar alerta
                self._cpu_history[container_name] = []

        return alerts

    def handle_unhealthy(self, container_id: str, container_name: str) -> RestartResult:
        """Gestiona un contenedor no saludable mediante reinicio.

        Reinicia el contenedor con un máximo de 3 intentos en un período
        de 5 minutos. Si se agotan los intentos, marca el contenedor
        como crítico.

        Args:
            container_id: ID del contenedor a reiniciar.
            container_name: Nombre del contenedor.

        Returns:
            RestartResult con el resultado del intento de reinicio.
        """
        now = datetime.now()
        window = timedelta(minutes=self.config.restart_window_minutes)

        # Limpiar historial de reinicios fuera de la ventana
        if container_id not in self._restart_history:
            self._restart_history[container_id] = []

        self._restart_history[container_id] = [
            t for t in self._restart_history[container_id]
            if now - t < window
        ]

        attempts_in_window = len(self._restart_history[container_id])

        # Verificar si se alcanzó el máximo de reintentos
        if attempts_in_window >= self.config.max_restart_attempts:
            # Marcar como crítico
            status = self._container_states.get(container_id)
            if status:
                status.state = ContainerState.CRITICAL
                self._container_states[container_id] = status

            alert = Alert(
                level="critical",
                container_name=container_name,
                message=(
                    f"Contenedor en estado crítico. "
                    f"Alcanzado máximo de {self.config.max_restart_attempts} "
                    f"reintentos fallidos en {self.config.restart_window_minutes} minutos. "
                    f"Se requiere intervención manual."
                ),
                timestamp=now,
            )
            self._emit_alert(alert)
            logger.critical(
                "Contenedor %s en estado CRÍTICO: %d reintentos fallidos en %d minutos",
                container_name,
                self.config.max_restart_attempts,
                self.config.restart_window_minutes,
            )

            return RestartResult(
                success=False,
                container_name=container_name,
                attempt_number=attempts_in_window,
                error_message=(
                    f"Máximo de reintentos alcanzado ({self.config.max_restart_attempts} "
                    f"en {self.config.restart_window_minutes} minutos)"
                ),
            )

        # Intentar reinicio
        attempt_number = attempts_in_window + 1

        # Actualizar estado a Restarting
        status = self._container_states.get(container_id)
        if status:
            status.state = ContainerState.RESTARTING
            self._container_states[container_id] = status

        logger.info(
            "Reiniciando contenedor %s (intento %d/%d)",
            container_name,
            attempt_number,
            self.config.max_restart_attempts,
        )

        try:
            container = self._docker_client.containers.get(container_id)
            container.restart(timeout=self.config.health_check_timeout_seconds)
            self._restart_history[container_id].append(now)

            # Verificar que el reinicio fue exitoso
            container.reload()
            if container.status == "running":
                if status:
                    status.state = ContainerState.HEALTHY
                    status.consecutive_failures = 0
                    status.restart_attempts = attempt_number
                    self._container_states[container_id] = status

                logger.info(
                    "Reinicio exitoso del contenedor %s (intento %d)",
                    container_name,
                    attempt_number,
                )
                return RestartResult(
                    success=True,
                    container_name=container_name,
                    attempt_number=attempt_number,
                )
            else:
                if status:
                    status.state = ContainerState.UNHEALTHY
                    status.restart_attempts = attempt_number
                    self._container_states[container_id] = status

                return RestartResult(
                    success=False,
                    container_name=container_name,
                    attempt_number=attempt_number,
                    error_message=f"Contenedor no alcanzó estado 'running' después del reinicio (estado: {container.status})",
                )

        except (APIError, NotFound) as e:
            self._restart_history[container_id].append(now)

            if status:
                status.state = ContainerState.UNHEALTHY
                status.restart_attempts = attempt_number
                self._container_states[container_id] = status

            error_msg = f"Error al reiniciar contenedor: {e}"
            logger.error("Error al reiniciar %s: %s", container_name, e)

            return RestartResult(
                success=False,
                container_name=container_name,
                attempt_number=attempt_number,
                error_message=error_msg,
            )

    def _emit_alert(self, alert: Alert) -> None:
        """Emite una alerta registrándola en el log.

        Args:
            alert: Alerta a emitir.
        """
        if alert.level == "critical":
            logger.critical(
                "ALERTA [%s] %s: %s",
                alert.level.upper(),
                alert.container_name,
                alert.message,
            )
        else:
            logger.warning(
                "ALERTA [%s] %s: %s",
                alert.level.upper(),
                alert.container_name,
                alert.message,
            )

    def _get_active_containers(self) -> list:
        """Obtiene la lista de contenedores activos.

        Returns:
            Lista de objetos Container de Docker.
        """
        try:
            return self._docker_client.containers.list()
        except (APIError, DockerException) as e:
            logger.error("Error al listar contenedores: %s", e)
            return []

    def run(self, pid_file: Optional[Path] = None) -> None:
        """Bucle principal de monitoreo.

        Ejecuta verificaciones de salud cada 30 segundos (configurable).
        Gestiona la conexión a Docker Engine con reintentos automáticos.
        Integra verificación de espacio en disco periódicamente.

        Args:
            pid_file: Ruta opcional al archivo PID. Si se proporciona,
                      se escribe el PID del proceso y se elimina al terminar.
        """
        logger.info("Iniciando monitor de salud (intervalo: %ds)", self.config.check_interval_seconds)

        # Configurar señales y PID
        self._setup_signal_handlers()
        if pid_file:
            self._write_pid_file(pid_file)

        self._running = True

        # Conexión inicial a Docker
        if not self._connect_docker():
            logger.error("No se pudo establecer conexión inicial a Docker Engine")
            # Intentar reconexión en el bucle principal
            self._docker_connected = False

        try:
            while self._running:
                try:
                    # Si no hay conexión a Docker, intentar reconectar
                    if not self._docker_connected:
                        if not self._handle_docker_disconnection():
                            if self._reconnect_attempts >= self.config.docker_max_reconnect_attempts:
                                logger.critical("Agotados todos los intentos de reconexión. Terminando monitor.")
                                break
                            # Esperar antes del siguiente intento
                            time.sleep(self.config.docker_reconnect_interval_seconds)
                            continue
                        # Reconexión exitosa, continuar con el ciclo normal

                    # Verificar que la conexión sigue activa
                    try:
                        self._docker_client.ping()
                    except DockerException:
                        logger.warning("Conexión a Docker perdida")
                        self._docker_connected = False
                        self._disconnected_since = datetime.now()
                        continue

                    # Obtener contenedores activos
                    containers = self._get_active_containers()

                    for container in containers:
                        if not self._running:
                            break

                        container_id = container.id
                        container_name = container.name

                        # Verificar salud
                        health_status = self.check_container_health(container_id)

                        # Obtener métricas de recursos
                        try:
                            metrics = self.check_resource_usage(container_id)
                            logger.info(
                                "Métricas %s: CPU=%.1f%%, MEM=%.1f%%, NET_RX=%d, NET_TX=%d",
                                container_name,
                                metrics.cpu_percent,
                                metrics.memory_percent,
                                metrics.network_rx_bytes,
                                metrics.network_tx_bytes,
                            )

                            # Evaluar alertas
                            alerts = self.evaluate_alerts(metrics, container_name)
                            for alert in alerts:
                                self._emit_alert(alert)

                        except (APIError, DockerException) as e:
                            logger.error(
                                "Error al obtener métricas de %s: %s",
                                container_name, e,
                            )

                        # Gestionar contenedores no saludables
                        if health_status.state == ContainerState.UNHEALTHY:
                            result = self.handle_unhealthy(container_id, container_name)
                            if not result.success:
                                logger.warning(
                                    "Reinicio fallido para %s: %s",
                                    container_name,
                                    result.error_message,
                                )

                    # Verificar espacio en disco
                    self._check_disk()

                    # Limpiar estados de contenedores que ya no existen
                    active_ids = {c.id for c in containers}
                    stale_ids = [
                        cid for cid in self._container_states
                        if cid not in active_ids
                    ]
                    for cid in stale_ids:
                        del self._container_states[cid]
                        if cid in self._cpu_history:
                            del self._cpu_history[cid]
                        if cid in self._restart_history:
                            del self._restart_history[cid]

                except DockerException as e:
                    logger.error("Error de Docker en ciclo de monitoreo: %s", e)
                    self._docker_connected = False
                    self._disconnected_since = datetime.now()

                except Exception as e:
                    logger.error("Error inesperado en ciclo de monitoreo: %s", e, exc_info=True)

                # Esperar hasta el siguiente ciclo
                time.sleep(self.config.check_interval_seconds)

        finally:
            self._remove_pid_file()
            logger.info("Monitor de salud detenido.")


def main():
    """Punto de entrada principal del monitor de salud.

    Soporta ejecución como proceso de fondo con archivo PID.
    Uso: python -m monitor.health_monitor [--pid-file <ruta>]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Monitor de salud Docker")
    parser.add_argument(
        "--pid-file",
        type=str,
        default=None,
        help="Ruta al archivo PID para rastrear el proceso",
    )
    args = parser.parse_args()

    pid_file = Path(args.pid_file) if args.pid_file else None

    config = load_config()
    monitor = HealthMonitor(config)
    monitor.run(pid_file=pid_file)


if __name__ == "__main__":
    main()
