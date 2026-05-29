"""Validación de rutas de volúmenes para contenedores Docker.

Este módulo verifica que las rutas configuradas para volúmenes persistentes
existen y tienen los permisos necesarios antes de iniciar contenedores.
"""

import os
from pathlib import Path

from monitor.models import ValidationResult


def validate_volume_path(path: str) -> ValidationResult:
    """Valida que una ruta de volumen existe y tiene permisos de lectura/escritura.

    Verifica:
    - Que la ruta existe en el sistema de archivos
    - Que la ruta tiene permiso de lectura
    - Que la ruta tiene permiso de escritura

    Args:
        path: Ruta del sistema de archivos a validar.

    Returns:
        ValidationResult con valid=True si la ruta es accesible con permisos r/w,
        o valid=False con errores descriptivos indicando la ruta y el permiso faltante.
    """
    errors: list[str] = []
    warnings: list[str] = []

    resolved_path = Path(path).resolve()

    # Verificar que la ruta existe
    if not resolved_path.exists():
        errors.append(
            f"La ruta de volúmenes no existe: {path}"
        )
        return ValidationResult(
            valid=False,
            errors=errors,
            warnings=warnings,
            file_path=str(resolved_path),
        )

    # Verificar permiso de lectura
    if not os.access(resolved_path, os.R_OK):
        errors.append(
            f"La ruta de volúmenes no tiene permiso de lectura: {path}"
        )

    # Verificar permiso de escritura
    if not os.access(resolved_path, os.W_OK):
        errors.append(
            f"La ruta de volúmenes no tiene permiso de escritura: {path}"
        )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        file_path=str(resolved_path),
    )
