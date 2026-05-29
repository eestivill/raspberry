"""Validador de configuración para archivos Docker Compose y entorno.

Valida la sintaxis y semántica de archivos de configuración antes de
aplicar cambios, reportando todos los errores encontrados (no se detiene
en el primero) con indicación de archivo y línea.

Uso como CLI:
    python -m monitor.config_validator [--base-path PATH]

Códigos de salida:
    0 - Validación exitosa (puede haber advertencias)
    3 - Errores de validación encontrados
"""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from monitor.models import ValidationResult, ServiceSecurityConfig


@dataclass
class SecurityWarning:
    """Advertencia de seguridad detectada en la configuración."""

    service_name: str
    issue: str
    file_path: str
    line_number: Optional[int] = None


class ConfigValidator:
    """Validador de archivos de configuración Docker Compose y entorno.

    Verifica sintaxis YAML, estructura de docker-compose, formato de
    archivos .env, configuración completa de servicios y cumplimiento
    de políticas de seguridad.
    """

    # Claves válidas de nivel superior en un docker-compose.yml
    VALID_TOP_LEVEL_KEYS = {
        "version", "services", "networks", "volumes",
        "configs", "secrets", "name",
    }

    # Claves válidas dentro de la definición de un servicio
    VALID_SERVICE_KEYS = {
        "image", "build", "container_name", "user", "networks",
        "ports", "volumes", "deploy", "security_opt", "restart",
        "healthcheck", "env_file", "environment", "command",
        "entrypoint", "depends_on", "labels", "logging",
        "cap_add", "cap_drop", "devices", "dns", "dns_search",
        "extra_hosts", "hostname", "links", "pid", "privileged",
        "read_only", "shm_size", "stdin_open", "stop_grace_period",
        "stop_signal", "sysctls", "tmpfs", "tty", "ulimits",
        "working_dir", "platform", "profiles", "pull_policy",
        "runtime", "scale", "storage_opt", "userns_mode",
        "init", "isolation", "extends", "external_links",
        "network_mode", "expose", "domainname", "ipc",
        "mac_address", "mem_swappiness", "oom_kill_disable",
        "oom_score_adj", "group_add", "cgroup_parent",
    }

    def validate_compose_file(self, file_path: str) -> ValidationResult:
        """Valida un archivo docker-compose.yml.

        Parsea el YAML y verifica que tiene una estructura válida de
        docker-compose: claves de nivel superior reconocidas, sección
        services con al menos un servicio (si existe), y estructura
        correcta de cada servicio.

        Args:
            file_path: Ruta al archivo docker-compose.yml.

        Returns:
            ValidationResult con errores y advertencias encontrados.
        """
        result = ValidationResult(valid=True, errors=[], warnings=[], file_path=file_path)

        # Verificar que el archivo existe
        path = Path(file_path)
        if not path.exists():
            result.valid = False
            result.errors.append(f"{file_path}: archivo no encontrado")
            return result

        # Leer contenido del archivo
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            result.valid = False
            result.errors.append(f"{file_path}: error al leer archivo: {e}")
            return result

        # Parsear YAML
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            result.valid = False
            line = self._extract_yaml_error_line(e)
            result.line_number = line
            line_info = f" (línea {line})" if line else ""
            result.errors.append(
                f"{file_path}{line_info}: error de sintaxis YAML: {e}"
            )
            return result

        # Un archivo vacío o solo con comentarios es válido pero genera advertencia
        if data is None:
            result.warnings.append(f"{file_path}: archivo vacío o solo comentarios")
            return result

        if not isinstance(data, dict):
            result.valid = False
            result.errors.append(
                f"{file_path}: el contenido debe ser un mapeo YAML, "
                f"se encontró {type(data).__name__}"
            )
            return result

        # Verificar claves de nivel superior
        lines = content.splitlines()
        for key in data:
            if key not in self.VALID_TOP_LEVEL_KEYS:
                line_num = self._find_key_line(lines, key)
                line_info = f" (línea {line_num})" if line_num else ""
                result.warnings.append(
                    f"{file_path}{line_info}: clave de nivel superior "
                    f"no reconocida: '{key}'"
                )

        # Validar sección services si existe
        if "services" in data:
            services = data["services"]
            if services is None:
                result.warnings.append(
                    f"{file_path}: sección 'services' está vacía"
                )
            elif not isinstance(services, dict):
                result.valid = False
                result.errors.append(
                    f"{file_path}: 'services' debe ser un mapeo, "
                    f"se encontró {type(services).__name__}"
                )
            else:
                for svc_name, svc_config in services.items():
                    self._validate_service_structure(
                        svc_name, svc_config, file_path, lines, result
                    )

        # Validar sección networks si existe
        if "networks" in data and data["networks"] is not None:
            if not isinstance(data["networks"], dict):
                result.valid = False
                result.errors.append(
                    f"{file_path}: 'networks' debe ser un mapeo"
                )

        # Validar sección volumes si existe
        if "volumes" in data and data["volumes"] is not None:
            if not isinstance(data["volumes"], dict):
                result.valid = False
                result.errors.append(
                    f"{file_path}: 'volumes' debe ser un mapeo"
                )

        return result

    def validate_env_file(self, file_path: str) -> ValidationResult:
        """Valida un archivo .env.

        Verifica que cada línea tiene formato clave=valor válido,
        detecta variables con valores vacíos y reporta líneas con
        formato incorrecto.

        Args:
            file_path: Ruta al archivo .env.

        Returns:
            ValidationResult con errores y advertencias encontrados.
        """
        result = ValidationResult(valid=True, errors=[], warnings=[], file_path=file_path)

        path = Path(file_path)
        if not path.exists():
            result.valid = False
            result.errors.append(f"{file_path}: archivo no encontrado")
            return result

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            result.valid = False
            result.errors.append(f"{file_path}: error al leer archivo: {e}")
            return result

        lines = content.splitlines()
        # Patrón para variable de entorno válida: CLAVE=valor
        env_pattern = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)')

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Líneas vacías y comentarios son válidos
            if not stripped or stripped.startswith("#"):
                continue

            match = env_pattern.match(stripped)
            if not match:
                result.valid = False
                result.errors.append(
                    f"{file_path} (línea {line_num}): formato inválido, "
                    f"se esperaba CLAVE=valor: '{stripped}'"
                )
                continue

            key = match.group(1)
            value = match.group(2)

            # Detectar variables con valor vacío
            if value.strip() == "":
                result.warnings.append(
                    f"{file_path} (línea {line_num}): variable '{key}' "
                    f"tiene valor vacío"
                )

        return result

    def validate_service_config(self, service_name: str, base_path: str = ".") -> ValidationResult:
        """Valida la configuración completa de un servicio.

        Verifica que el servicio tiene un directorio en services/,
        un archivo docker-compose.override.yml válido, y que la
        configuración incluye los campos obligatorios.

        Args:
            service_name: Nombre del servicio a validar.
            base_path: Ruta base del proyecto.

        Returns:
            ValidationResult con errores y advertencias encontrados.
        """
        result = ValidationResult(
            valid=True, errors=[], warnings=[], file_path=f"services/{service_name}/"
        )

        base = Path(base_path)
        service_dir = base / "services" / service_name

        # Verificar que el directorio del servicio existe
        if not service_dir.exists():
            result.valid = False
            result.errors.append(
                f"services/{service_name}/: directorio de servicio no encontrado"
            )
            return result

        # Verificar archivo override
        override_file = service_dir / "docker-compose.override.yml"
        if not override_file.exists():
            result.valid = False
            result.errors.append(
                f"services/{service_name}/: falta docker-compose.override.yml"
            )
            return result

        # Validar el archivo compose del servicio
        compose_result = self.validate_compose_file(str(override_file))
        result.errors.extend(compose_result.errors)
        result.warnings.extend(compose_result.warnings)
        if not compose_result.valid:
            result.valid = False

        # Verificar campos obligatorios del servicio
        try:
            content = override_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except (OSError, yaml.YAMLError):
            # Ya reportado por validate_compose_file
            return result

        if data is None or "services" not in data:
            result.valid = False
            result.errors.append(
                f"services/{service_name}/docker-compose.override.yml: "
                f"no define ningún servicio"
            )
            return result

        services = data.get("services", {})
        if not isinstance(services, dict):
            return result

        lines = content.splitlines()

        for svc_name, svc_config in services.items():
            if svc_config is None:
                result.valid = False
                result.errors.append(
                    f"services/{service_name}/docker-compose.override.yml: "
                    f"servicio '{svc_name}' está vacío"
                )
                continue

            # Verificar imagen definida
            if "image" not in svc_config and "build" not in svc_config:
                line_num = self._find_key_line(lines, svc_name)
                line_info = f" (línea {line_num})" if line_num else ""
                result.valid = False
                result.errors.append(
                    f"services/{service_name}/docker-compose.override.yml{line_info}: "
                    f"servicio '{svc_name}' no define 'image' ni 'build'"
                )

            # Verificar red definida
            if "networks" not in svc_config:
                result.warnings.append(
                    f"services/{service_name}/docker-compose.override.yml: "
                    f"servicio '{svc_name}' no define 'networks'"
                )

            # Verificar health check
            if "healthcheck" not in svc_config:
                result.warnings.append(
                    f"services/{service_name}/docker-compose.override.yml: "
                    f"servicio '{svc_name}' no define 'healthcheck'"
                )

            # Verificar seguridad
            security_warnings = self._check_service_security(
                svc_name, svc_config,
                f"services/{service_name}/docker-compose.override.yml",
                lines
            )
            for warning in security_warnings:
                if warning.issue.startswith("[ERROR]"):
                    result.valid = False
                    result.errors.append(
                        f"{warning.file_path}"
                        f"{f' (línea {warning.line_number})' if warning.line_number else ''}: "
                        f"{warning.issue}"
                    )
                else:
                    result.warnings.append(
                        f"{warning.file_path}"
                        f"{f' (línea {warning.line_number})' if warning.line_number else ''}: "
                        f"{warning.issue}"
                    )

        return result

    def check_security_compliance(
        self, compose_config: dict, file_path: str = "", lines: list[str] | None = None
    ) -> list[SecurityWarning]:
        """Verifica cumplimiento de políticas de seguridad.

        Comprueba para cada servicio:
        - Usuario no-root (a menos que haya justificación documentada)
        - no-new-privileges habilitado
        - Puertos vinculados a 127.0.0.1
        - Política de reinicio con máximo de reintentos
        - Límites de recursos (CPU y memoria)
        - Imagen con versión fija (no 'latest' ni sin etiqueta)

        Args:
            compose_config: Diccionario con la configuración parseada del
                           archivo docker-compose.
            file_path: Ruta del archivo para incluir en los mensajes.
            lines: Líneas del archivo para reportar números de línea.

        Returns:
            Lista de SecurityWarning con los problemas encontrados.
        """
        warnings: list[SecurityWarning] = []
        file_lines = lines if lines is not None else []

        services = compose_config.get("services")
        if not services or not isinstance(services, dict):
            return warnings

        for svc_name, svc_config in services.items():
            if svc_config is None:
                continue

            svc_warnings = self._check_service_security(
                svc_name, svc_config, file_path, file_lines
            )
            warnings.extend(svc_warnings)

        return warnings

    def validate_volume_path(self, volume_path: str) -> ValidationResult:
        """Valida que la ruta de volúmenes existe y tiene permisos adecuados.

        Args:
            volume_path: Ruta del directorio de volúmenes.

        Returns:
            ValidationResult con errores si la ruta es inválida.
        """
        result = ValidationResult(
            valid=True, errors=[], warnings=[], file_path=volume_path
        )

        path = Path(volume_path)

        if not path.exists():
            result.valid = False
            result.errors.append(
                f"{volume_path}: ruta no existe"
            )
            return result

        if not path.is_dir():
            result.valid = False
            result.errors.append(
                f"{volume_path}: la ruta no es un directorio"
            )
            return result

        if not os.access(volume_path, os.R_OK):
            result.valid = False
            result.errors.append(
                f"{volume_path}: sin permiso de lectura"
            )

        if not os.access(volume_path, os.W_OK):
            result.valid = False
            result.errors.append(
                f"{volume_path}: sin permiso de escritura"
            )

        return result

    # -------------------------------------------------------------------------
    # Métodos internos
    # -------------------------------------------------------------------------

    def _validate_service_structure(
        self,
        svc_name: str,
        svc_config: dict | None,
        file_path: str,
        lines: list[str],
        result: ValidationResult,
    ) -> None:
        """Valida la estructura interna de un servicio."""
        if svc_config is None:
            result.warnings.append(
                f"{file_path}: servicio '{svc_name}' está vacío"
            )
            return

        if not isinstance(svc_config, dict):
            result.valid = False
            line_num = self._find_key_line(lines, svc_name)
            line_info = f" (línea {line_num})" if line_num else ""
            result.errors.append(
                f"{file_path}{line_info}: servicio '{svc_name}' debe ser "
                f"un mapeo, se encontró {type(svc_config).__name__}"
            )
            return

        # Verificar que el servicio tiene imagen o build
        if "image" not in svc_config and "build" not in svc_config:
            line_num = self._find_key_line(lines, svc_name)
            line_info = f" (línea {line_num})" if line_num else ""
            result.warnings.append(
                f"{file_path}{line_info}: servicio '{svc_name}' no define "
                f"'image' ni 'build'"
            )

    def _check_service_security(
        self,
        svc_name: str,
        svc_config: dict,
        file_path: str,
        lines: list[str],
    ) -> list[SecurityWarning]:
        """Verifica políticas de seguridad de un servicio individual."""
        warnings: list[SecurityWarning] = []

        # 1. Verificar usuario no-root (Req 7.1, 7.8)
        user = svc_config.get("user")
        has_root_exception = self._has_root_exception(svc_config, lines)

        if user is None and not has_root_exception:
            line_num = self._find_key_line(lines, svc_name) if lines else None
            warnings.append(SecurityWarning(
                service_name=svc_name,
                issue=f"servicio '{svc_name}' no define usuario no-root ('user')",
                file_path=file_path,
                line_number=line_num,
            ))
        elif user is not None:
            # Verificar que no es root (UID 0)
            user_str = str(user)
            if user_str == "0" or user_str.startswith("0:") or user_str == "root":
                if not has_root_exception:
                    line_num = self._find_key_line(lines, "user") if lines else None
                    warnings.append(SecurityWarning(
                        service_name=svc_name,
                        issue=(
                            f"[ERROR] servicio '{svc_name}' ejecuta como root "
                            f"sin justificación documentada (ROOT_EXCEPTION:)"
                        ),
                        file_path=file_path,
                        line_number=line_num,
                    ))

        # 2. Verificar no-new-privileges (Req 7.3)
        security_opt = svc_config.get("security_opt", [])
        has_no_new_privileges = False
        if isinstance(security_opt, list):
            for opt in security_opt:
                if isinstance(opt, str) and "no-new-privileges" in opt:
                    # Acepta "no-new-privileges:true" o "no-new-privileges"
                    if "false" not in opt.lower():
                        has_no_new_privileges = True
                        break

        if not has_no_new_privileges:
            line_num = self._find_key_line(lines, "security_opt") if lines else None
            warnings.append(SecurityWarning(
                service_name=svc_name,
                issue=(
                    f"servicio '{svc_name}' no tiene "
                    f"'no-new-privileges' habilitado en security_opt"
                ),
                file_path=file_path,
                line_number=line_num,
            ))

        # 3. Verificar puertos vinculados a localhost (Req 7.4)
        ports = svc_config.get("ports", [])
        if isinstance(ports, list):
            for port in ports:
                port_str = str(port)
                if not self._is_localhost_port(port_str):
                    line_num = self._find_key_line(lines, "ports") if lines else None
                    warnings.append(SecurityWarning(
                        service_name=svc_name,
                        issue=(
                            f"servicio '{svc_name}' expone puerto '{port_str}' "
                            f"sin vincular a 127.0.0.1 (localhost)"
                        ),
                        file_path=file_path,
                        line_number=line_num,
                    ))

        # 4. Verificar política de reinicio (Req 7.5)
        restart = svc_config.get("restart")
        if restart is None:
            line_num = self._find_key_line(lines, svc_name) if lines else None
            warnings.append(SecurityWarning(
                service_name=svc_name,
                issue=(
                    f"servicio '{svc_name}' no define política de reinicio "
                    f"('restart')"
                ),
                file_path=file_path,
                line_number=line_num,
            ))
        elif isinstance(restart, str):
            if restart == "always" or restart == "unless-stopped":
                line_num = self._find_key_line(lines, "restart") if lines else None
                warnings.append(SecurityWarning(
                    service_name=svc_name,
                    issue=(
                        f"servicio '{svc_name}' usa política de reinicio "
                        f"'{restart}' sin límite de reintentos (se recomienda "
                        f"'on-failure:5')"
                    ),
                    file_path=file_path,
                    line_number=line_num,
                ))
            elif restart.startswith("on-failure:"):
                try:
                    max_retries = int(restart.split(":")[1])
                    if max_retries > 5:
                        line_num = self._find_key_line(lines, "restart") if lines else None
                        warnings.append(SecurityWarning(
                            service_name=svc_name,
                            issue=(
                                f"servicio '{svc_name}' tiene política de reinicio "
                                f"con {max_retries} reintentos (máximo recomendado: 5)"
                            ),
                            file_path=file_path,
                            line_number=line_num,
                        ))
                except (ValueError, IndexError):
                    pass

        # 5. Verificar límites de recursos (Req 7.2, 7.9)
        deploy = svc_config.get("deploy", {})
        has_resource_limits = False
        if isinstance(deploy, dict):
            resources = deploy.get("resources", {})
            if isinstance(resources, dict):
                limits = resources.get("limits", {})
                if isinstance(limits, dict):
                    has_cpus = "cpus" in limits
                    has_memory = "memory" in limits
                    has_resource_limits = has_cpus and has_memory

                    if not has_cpus:
                        line_num = self._find_key_line(lines, "limits") if lines else None
                        warnings.append(SecurityWarning(
                            service_name=svc_name,
                            issue=(
                                f"servicio '{svc_name}' no define límite de CPU "
                                f"(se aplicará por defecto: 1.0)"
                            ),
                            file_path=file_path,
                            line_number=line_num,
                        ))
                    if not has_memory:
                        line_num = self._find_key_line(lines, "limits") if lines else None
                        warnings.append(SecurityWarning(
                            service_name=svc_name,
                            issue=(
                                f"servicio '{svc_name}' no define límite de memoria "
                                f"(se aplicará por defecto: 512M)"
                            ),
                            file_path=file_path,
                            line_number=line_num,
                        ))

        if not has_resource_limits and not isinstance(deploy, dict):
            line_num = self._find_key_line(lines, svc_name) if lines else None
            warnings.append(SecurityWarning(
                service_name=svc_name,
                issue=(
                    f"servicio '{svc_name}' no define límites de recursos "
                    f"(se aplicarán por defecto: 1 CPU, 512M RAM)"
                ),
                file_path=file_path,
                line_number=line_num,
            ))
        elif not has_resource_limits:
            # deploy exists but no proper resource limits
            resources = deploy.get("resources", {}) if isinstance(deploy, dict) else {}
            if not isinstance(resources, dict) or "limits" not in resources:
                line_num = self._find_key_line(lines, "deploy") if lines else None
                warnings.append(SecurityWarning(
                    service_name=svc_name,
                    issue=(
                        f"servicio '{svc_name}' no define límites de recursos "
                        f"(se aplicarán por defecto: 1 CPU, 512M RAM)"
                    ),
                    file_path=file_path,
                    line_number=line_num,
                ))

        # 6. Verificar imagen con versión fija (Req 7.6)
        image = svc_config.get("image")
        if image is not None:
            image_str = str(image)
            if self._is_unpinned_image(image_str):
                line_num = self._find_key_line(lines, "image") if lines else None
                warnings.append(SecurityWarning(
                    service_name=svc_name,
                    issue=(
                        f"servicio '{svc_name}' usa imagen '{image_str}' "
                        f"sin versión fija (se recomienda fijar una versión específica)"
                    ),
                    file_path=file_path,
                    line_number=line_num,
                ))

        return warnings

    def _is_localhost_port(self, port_str: str) -> bool:
        """Verifica si un puerto está vinculado a localhost (127.0.0.1).

        Formatos aceptados como localhost:
        - "127.0.0.1:8080:8080"
        - "127.0.0.1:8080:8080/tcp"

        Formatos NO localhost:
        - "8080:8080" (se vincula a 0.0.0.0)
        - "0.0.0.0:8080:8080"
        - "192.168.1.1:8080:8080"
        """
        port_str = port_str.strip()

        # Si empieza con 127.0.0.1, es localhost
        if port_str.startswith("127.0.0.1:"):
            return True

        # Si tiene formato IP:host_port:container_port, verificar la IP
        parts = port_str.split(":")
        if len(parts) == 3:
            # Formato IP:host_port:container_port
            ip = parts[0]
            return ip == "127.0.0.1"

        # Si solo tiene host_port:container_port, se vincula a 0.0.0.0
        # (no es localhost)
        return False

    def _is_unpinned_image(self, image: str) -> bool:
        """Verifica si una imagen no tiene versión fija.

        Retorna True si la imagen usa 'latest' o no tiene etiqueta.
        """
        # Separar registry/nombre de la etiqueta
        # Manejar imágenes con registry: registry.example.com/image:tag
        # y sin registry: image:tag o library/image:tag

        # Si contiene @sha256:, está fijada por digest
        if "@sha256:" in image:
            return False

        # Separar por ":" para encontrar la etiqueta
        # Pero cuidado con el puerto del registry: registry:5000/image:tag
        parts = image.split("/")
        last_part = parts[-1]

        if ":" in last_part:
            tag = last_part.split(":")[-1]
            # Verificar si es "latest"
            return tag == "latest"
        else:
            # No tiene etiqueta, equivale a "latest"
            return True

    def _has_root_exception(self, svc_config: dict, lines: list[str]) -> bool:
        """Verifica si hay una justificación ROOT_EXCEPTION en los comentarios."""
        # Buscar en las líneas del archivo el patrón ROOT_EXCEPTION:
        for line in lines:
            if "ROOT_EXCEPTION:" in line and line.strip().startswith("#"):
                return True
        return False

    def _find_key_line(self, lines: list[str], key: str) -> Optional[int]:
        """Busca la línea donde aparece una clave YAML.

        Args:
            lines: Líneas del archivo.
            key: Clave a buscar.

        Returns:
            Número de línea (1-indexed) o None si no se encuentra.
        """
        # Buscar patrón "key:" al inicio de línea (con posible indentación)
        pattern = re.compile(rf'^\s*{re.escape(key)}\s*:')
        for i, line in enumerate(lines, start=1):
            if pattern.match(line):
                return i
        return None

    def _extract_yaml_error_line(self, error: yaml.YAMLError) -> Optional[int]:
        """Extrae el número de línea de un error YAML.

        Args:
            error: Excepción YAML.

        Returns:
            Número de línea (1-indexed) o None.
        """
        if hasattr(error, "problem_mark") and error.problem_mark is not None:
            return error.problem_mark.line + 1
        return None



def run_validation(base_path: str = ".") -> int:
    """Ejecuta validación completa del proyecto.

    Valida el archivo docker-compose.yml principal, los archivos override
    de servicios, el archivo .env, y verifica cumplimiento de seguridad.

    Args:
        base_path: Ruta base del proyecto.

    Returns:
        Código de salida: 0 si no hay errores, 3 si hay errores.
    """
    validator = ConfigValidator()
    base = Path(base_path)
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. Validar docker-compose.yml principal
    compose_file = base / "docker-compose.yml"
    if compose_file.exists():
        result = validator.validate_compose_file(str(compose_file))
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

        # Verificar seguridad en el archivo principal
        if result.valid:
            try:
                content = compose_file.read_text(encoding="utf-8")
                data = yaml.safe_load(content)
                if data and isinstance(data, dict):
                    file_lines = content.splitlines()
                    sec_warnings = validator.check_security_compliance(
                        data, str(compose_file), file_lines
                    )
                    for sw in sec_warnings:
                        line_info = f" (línea {sw.line_number})" if sw.line_number else ""
                        msg = f"{sw.file_path}{line_info}: {sw.issue}"
                        if sw.issue.startswith("[ERROR]"):
                            all_errors.append(msg)
                        else:
                            all_warnings.append(msg)
            except (OSError, yaml.YAMLError):
                pass

    # 2. Validar archivos override de servicios
    services_dir = base / "services"
    if services_dir.exists():
        for service_dir in sorted(services_dir.iterdir()):
            if not service_dir.is_dir():
                continue
            if service_dir.name == "service-template":
                continue

            override_file = service_dir / "docker-compose.override.yml"
            if override_file.exists():
                result = validator.validate_compose_file(str(override_file))
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)

                # Verificar seguridad en cada servicio
                if result.valid:
                    try:
                        content = override_file.read_text(encoding="utf-8")
                        data = yaml.safe_load(content)
                        if data and isinstance(data, dict):
                            file_lines = content.splitlines()
                            sec_warnings = validator.check_security_compliance(
                                data, str(override_file), file_lines
                            )
                            for sw in sec_warnings:
                                line_info = (
                                    f" (línea {sw.line_number})"
                                    if sw.line_number
                                    else ""
                                )
                                msg = f"{sw.file_path}{line_info}: {sw.issue}"
                                if sw.issue.startswith("[ERROR]"):
                                    all_errors.append(msg)
                                else:
                                    all_warnings.append(msg)
                    except (OSError, yaml.YAMLError):
                        pass

    # 3. Validar archivo .env si existe
    env_file = base / ".env"
    if env_file.exists():
        result = validator.validate_env_file(str(env_file))
        all_errors.extend(result.errors)
        all_warnings.extend(result.warnings)

    # 4. Mostrar resultados
    for warning in all_warnings:
        print(f"[WARN]  {warning}", file=sys.stderr)

    for error in all_errors:
        print(f"[ERROR] {error}", file=sys.stderr)

    if all_errors:
        print(
            f"\nValidación fallida: {len(all_errors)} error(es), "
            f"{len(all_warnings)} advertencia(s).",
            file=sys.stderr,
        )
        return 3

    if all_warnings:
        print(
            f"\nValidación exitosa con {len(all_warnings)} advertencia(s).",
            file=sys.stderr,
        )
    else:
        print("\nValidación exitosa sin errores ni advertencias.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validador de configuración Docker Compose"
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Ruta base del proyecto (default: directorio actual)",
    )
    args = parser.parse_args()

    sys.exit(run_validation(args.base_path))
