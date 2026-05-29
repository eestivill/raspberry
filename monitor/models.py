"""Modelos de datos para el sistema de monitoreo de infraestructura Docker."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ContainerState(Enum):
    """Estados posibles de un contenedor en el ciclo de monitoreo."""

    HEALTHY = "healthy"
    CHECK_FAILED = "check_failed"
    UNHEALTHY = "unhealthy"
    RESTARTING = "restarting"
    CRITICAL = "critical"


@dataclass
class MonitorConfig:
    """Configuración del monitor de salud."""

    check_interval_seconds: int = 30
    health_check_timeout_seconds: int = 5
    max_consecutive_failures: int = 3
    max_restart_attempts: int = 3
    restart_window_minutes: int = 5
    memory_alert_threshold_percent: float = 85.0
    cpu_alert_threshold_percent: float = 90.0
    cpu_alert_consecutive_cycles: int = 3
    docker_reconnect_interval_seconds: int = 60
    docker_max_reconnect_attempts: int = 10
    disk_check_interval_seconds: int = 60
    disk_low_threshold_percent: float = 10.0
    disk_notification_cooldown_minutes: int = 10
    log_file: str = "../logs/health.log"
    log_max_size_mb: int = 10
    log_backup_count: int = 3


@dataclass
class ResourceMetrics:
    """Métricas de uso de recursos de un contenedor."""

    container_name: str
    cpu_percent: float
    memory_percent: float
    memory_usage_mb: float
    memory_limit_mb: float
    network_rx_bytes: int
    network_tx_bytes: int
    timestamp: datetime


@dataclass
class HealthStatus:
    """Estado de salud de un contenedor."""

    container_id: str
    container_name: str
    state: ContainerState
    consecutive_failures: int
    restart_attempts: int
    last_check: datetime
    last_state_change: datetime


@dataclass
class Alert:
    """Alerta generada por el monitor."""

    level: str  # "warning" | "critical"
    container_name: str
    message: str
    timestamp: datetime
    metric_value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class ValidationResult:
    """Resultado de validación de configuración."""

    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    file_path: str = ""
    line_number: Optional[int] = None


@dataclass
class DiskStatus:
    """Estado del espacio en disco."""

    path: str
    total_mb: float
    used_mb: float
    available_mb: float
    usage_percent: float
    is_low: bool


@dataclass
class RestartResult:
    """Resultado de un intento de reinicio de contenedor."""

    success: bool
    container_name: str
    attempt_number: int
    error_message: Optional[str] = None


@dataclass
class ServiceSecurityConfig:
    """Configuración de seguridad de un servicio."""

    user_non_root: bool = True
    no_new_privileges: bool = True
    cpu_limit: str = "1.0"
    memory_limit: str = "512m"
    restart_policy_max_retries: int = 5
    bind_localhost_only: bool = True
    image_version_pinned: bool = True
    root_exception_justification: Optional[str] = None
