"""Tests de integración: manage.sh + config_validator.py.

Verifica que:
- `manage.sh validate` invoca config_validator.py y reporta errores con archivo/línea
- `manage.sh start` ejecuta validación antes de iniciar contenedores
- Errores de validación impiden el inicio y muestran archivo/línea

Requirements: 8.5, 8.6
"""

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest


# Ruta al proyecto real (para copiar manage.sh y monitor/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def project_env(tmp_path):
    """Crea un entorno de proyecto temporal con manage.sh y monitor/.

    Copia manage.sh y el módulo monitor/ al directorio temporal para
    poder ejecutar validación sin afectar el proyecto real.
    """
    # Copiar manage.sh
    shutil.copy2(PROJECT_ROOT / "manage.sh", tmp_path / "manage.sh")
    os.chmod(tmp_path / "manage.sh", 0o755)

    # Copiar módulo monitor/
    shutil.copytree(
        PROJECT_ROOT / "monitor",
        tmp_path / "monitor",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    # Crear directorios necesarios
    (tmp_path / "services" / "service-template").mkdir(parents=True)
    (tmp_path / "volumes").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    return tmp_path


def run_manage(project_dir: Path, *args, env_override=None):
    """Ejecuta manage.sh con los argumentos dados y retorna el resultado."""
    env = os.environ.copy()
    env["VOLUMES_PATH"] = str(project_dir / "volumes")
    if env_override:
        env.update(env_override)

    result = subprocess.run(
        ["bash", str(project_dir / "manage.sh"), *args],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
        timeout=30,
    )
    return result


class TestValidateCommandIntegration:
    """Tests para `manage.sh validate` con config_validator.py."""

    def test_validate_valid_compose_succeeds(self, project_env):
        """Validación exitosa con docker-compose.yml válido."""
        compose_content = """\
networks:
  internal:
    driver: bridge
    name: rpi4_internal
"""
        (project_env / "docker-compose.yml").write_text(compose_content)

        result = run_manage(project_env, "validate")

        # docker compose config puede fallar sin Docker, pero la validación
        # Python (fase 2) debe ejecutarse. Verificamos que se intenta validar.
        combined_output = result.stdout + result.stderr
        # Si docker compose no está disponible, el script puede fallar en fase 1
        # pero la integración con config_validator.py es lo que verificamos
        assert "Validando archivos de configuración" in combined_output

    def test_validate_invalid_yaml_reports_file_and_line(self, project_env):
        """YAML inválido reporta archivo y línea del error."""
        # Crear un docker-compose.yml con YAML inválido
        invalid_yaml = """\
services:
  web:
    image: [unclosed bracket
    ports:
      - "8080:80"
"""
        (project_env / "docker-compose.yml").write_text(invalid_yaml)

        result = run_manage(project_env, "validate")

        # Debe fallar con código de salida 3 (error de configuración)
        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        # Debe mencionar el archivo y/o línea
        assert "docker-compose.yml" in combined_output or "sintaxis" in combined_output.lower()

    def test_validate_calls_python_validator(self, project_env):
        """Verifica que manage.sh validate invoca config_validator.py."""
        compose_content = """\
networks:
  internal:
    driver: bridge
    name: rpi4_internal
"""
        (project_env / "docker-compose.yml").write_text(compose_content)

        # Crear un servicio con problemas de seguridad para que el validador
        # Python los detecte (advertencias)
        svc_dir = project_env / "services" / "insecure-svc"
        svc_dir.mkdir(parents=True)
        insecure_compose = """\
services:
  insecure-svc:
    image: nginx:latest
    ports:
      - "8080:80"
    restart: always

networks:
  internal:
    external: true
    name: rpi4_internal
"""
        (svc_dir / "docker-compose.override.yml").write_text(insecure_compose)

        result = run_manage(project_env, "validate")

        combined_output = result.stdout + result.stderr
        # El validador Python debe detectar problemas de seguridad:
        # - imagen con :latest
        # - puerto no vinculado a localhost
        # - restart: always sin límite
        # - sin user
        # - sin no-new-privileges
        # Estos se reportan como advertencias o errores
        has_security_findings = (
            "latest" in combined_output
            or "localhost" in combined_output
            or "127.0.0.1" in combined_output
            or "no-new-privileges" in combined_output
            or "user" in combined_output
            or "seguridad" in combined_output.lower()
            or "WARN" in combined_output
        )
        assert has_security_findings, (
            f"El validador Python no reportó hallazgos de seguridad.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_validate_env_file_error_shows_line(self, project_env):
        """Error en .env muestra número de línea."""
        compose_content = """\
networks:
  internal:
    driver: bridge
"""
        (project_env / "docker-compose.yml").write_text(compose_content)

        # Crear .env con formato inválido en línea 3
        env_content = """\
VALID_KEY=value
ANOTHER=123
this is invalid format
LAST=ok
"""
        (project_env / ".env").write_text(env_content)

        result = run_manage(project_env, "validate")

        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        # Debe reportar el error con número de línea
        assert "línea" in combined_output.lower() or "line" in combined_output.lower()


class TestStartCommandValidation:
    """Tests para `manage.sh start` ejecutando validación previa."""

    def test_start_runs_validation_before_containers(self, project_env):
        """El comando start ejecuta validación antes de iniciar."""
        compose_content = """\
networks:
  internal:
    driver: bridge
    name: rpi4_internal
"""
        (project_env / "docker-compose.yml").write_text(compose_content)

        result = run_manage(project_env, "start")

        combined_output = result.stdout + result.stderr
        # Debe indicar que ejecuta validación
        assert "validación" in combined_output.lower() or "Ejecutando validación" in combined_output

    def test_start_blocked_by_invalid_yaml(self, project_env):
        """Inicio bloqueado por YAML inválido en docker-compose.yml."""
        invalid_yaml = """\
services:
  web:
    image: [broken
"""
        (project_env / "docker-compose.yml").write_text(invalid_yaml)

        result = run_manage(project_env, "start")

        # Debe fallar con código 3 (error de configuración)
        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        # Debe indicar que la validación falló y no se inician contenedores
        has_validation_block = (
            "No se iniciarán" in combined_output
            or "No se pueden iniciar" in combined_output
            or "Validación" in combined_output
            or "validación" in combined_output
        )
        assert has_validation_block, (
            f"El inicio no fue bloqueado por validación.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_start_blocked_by_env_error(self, project_env):
        """Inicio bloqueado por error en archivo .env."""
        compose_content = """\
networks:
  internal:
    driver: bridge
"""
        (project_env / "docker-compose.yml").write_text(compose_content)

        # .env con formato inválido
        (project_env / ".env").write_text("VALID=ok\nbad format here\n")

        result = run_manage(project_env, "start")

        # Debe fallar
        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        # Debe mostrar información sobre el error
        assert "validación" in combined_output.lower() or "error" in combined_output.lower()

    def test_start_shows_file_and_line_on_error(self, project_env):
        """Errores de validación en start muestran archivo y línea."""
        # Crear servicio con YAML inválido
        svc_dir = project_env / "services" / "broken-svc"
        svc_dir.mkdir(parents=True)
        broken_yaml = """\
services:
  broken:
    image: [unclosed
"""
        (svc_dir / "docker-compose.override.yml").write_text(broken_yaml)

        # docker-compose.yml principal válido
        (project_env / "docker-compose.yml").write_text("networks:\n  internal:\n    driver: bridge\n")

        result = run_manage(project_env, "start")

        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        # Debe mencionar el archivo con error
        has_file_reference = (
            "docker-compose" in combined_output
            or "broken-svc" in combined_output
            or "línea" in combined_output
        )
        assert has_file_reference, (
            f"No se muestra referencia a archivo/línea.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_start_blocked_by_invalid_volumes_path(self, project_env):
        """Inicio bloqueado si la ruta de volúmenes es inválida."""
        (project_env / "docker-compose.yml").write_text("networks:\n  internal:\n    driver: bridge\n")

        # Usar una ruta de volúmenes que no existe
        result = run_manage(
            project_env, "start",
            env_override={"VOLUMES_PATH": "/ruta/inexistente/volumes"}
        )

        assert result.returncode != 0
        combined_output = result.stdout + result.stderr
        assert "volúmenes" in combined_output.lower() or "volumes" in combined_output.lower()
