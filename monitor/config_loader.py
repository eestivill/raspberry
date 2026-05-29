"""Módulo de carga de configuración del monitor de salud.

Parsea el archivo config.yml y retorna una instancia de MonitorConfig
con todos los parámetros configurables del sistema de monitoreo.
"""

import os
from pathlib import Path

import yaml

from monitor.models import MonitorConfig


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yml"


def load_config(config_path: str | Path | None = None) -> MonitorConfig:
    """Carga la configuración del monitor desde un archivo YAML.

    Args:
        config_path: Ruta al archivo de configuración YAML.
                     Si es None, usa el archivo config.yml por defecto
                     en el directorio del monitor.

    Returns:
        MonitorConfig con los valores del archivo o valores por defecto
        si algún parámetro no está presente.

    Raises:
        FileNotFoundError: Si el archivo de configuración no existe.
        yaml.YAMLError: Si el archivo YAML tiene errores de sintaxis.
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Archivo de configuración no encontrado: {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return MonitorConfig()

    return _parse_config(raw)


def _parse_config(raw: dict) -> MonitorConfig:
    """Parsea el diccionario YAML crudo y retorna un MonitorConfig.

    Extrae los valores de las secciones 'monitor', 'alerts', 'docker',
    'disk' y 'logging', aplicando valores por defecto cuando un campo
    no está presente.

    Args:
        raw: Diccionario resultado de parsear el YAML.

    Returns:
        MonitorConfig con los valores extraídos.
    """
    monitor = raw.get("monitor", {})
    alerts = raw.get("alerts", {})
    docker = raw.get("docker", {})
    disk = raw.get("disk", {})
    logging_cfg = raw.get("logging", {})

    return MonitorConfig(
        check_interval_seconds=monitor.get("check_interval", 30),
        health_check_timeout_seconds=monitor.get("health_check_timeout", 5),
        max_consecutive_failures=monitor.get("max_failures", 3),
        max_restart_attempts=monitor.get("max_restarts", 3),
        restart_window_minutes=monitor.get("restart_window", 300) // 60,
        memory_alert_threshold_percent=float(alerts.get("memory_threshold", 85)),
        cpu_alert_threshold_percent=float(alerts.get("cpu_threshold", 90)),
        cpu_alert_consecutive_cycles=alerts.get("cpu_consecutive_cycles", 3),
        docker_reconnect_interval_seconds=docker.get("reconnect_interval", 60),
        docker_max_reconnect_attempts=docker.get("max_reconnect_attempts", 10),
        disk_check_interval_seconds=disk.get("check_interval", 60),
        disk_low_threshold_percent=float(alerts.get("disk_low_threshold", 10)),
        disk_notification_cooldown_minutes=disk.get("notification_cooldown", 600) // 60,
        log_file=logging_cfg.get("file", "../logs/health.log"),
        log_max_size_mb=logging_cfg.get("max_size_mb", 10),
        log_backup_count=logging_cfg.get("backup_count", 3),
    )
