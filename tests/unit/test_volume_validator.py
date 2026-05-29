"""Tests unitarios para la validación de rutas de volúmenes."""

import os
import stat
from pathlib import Path

import pytest

from monitor.models import ValidationResult
from monitor.volume_validator import validate_volume_path


class TestValidateVolumePath:
    """Tests para la función validate_volume_path."""

    def test_valid_path_with_rw_permissions(self, tmp_path):
        """Una ruta existente con permisos r/w retorna valid=True."""
        result = validate_volume_path(str(tmp_path))

        assert result.valid is True
        assert result.errors == []

    def test_nonexistent_path_returns_invalid(self):
        """Una ruta inexistente retorna valid=False con error descriptivo."""
        fake_path = "/ruta/inexistente/volumen"
        result = validate_volume_path(fake_path)

        assert result.valid is False
        assert len(result.errors) == 1
        assert "no existe" in result.errors[0]
        assert fake_path in result.errors[0]

    def test_path_without_read_permission(self, tmp_path):
        """Una ruta sin permiso de lectura retorna error indicando permiso faltante."""
        no_read_dir = tmp_path / "no_read"
        no_read_dir.mkdir()
        # Quitar permiso de lectura
        no_read_dir.chmod(0o200)

        try:
            result = validate_volume_path(str(no_read_dir))

            assert result.valid is False
            assert any("lectura" in e for e in result.errors)
            assert any(str(no_read_dir) in e or "no_read" in e for e in result.errors)
        finally:
            # Restaurar permisos para limpieza
            no_read_dir.chmod(0o755)

    def test_path_without_write_permission(self, tmp_path):
        """Una ruta sin permiso de escritura retorna error indicando permiso faltante."""
        no_write_dir = tmp_path / "no_write"
        no_write_dir.mkdir()
        # Quitar permiso de escritura
        no_write_dir.chmod(0o555)

        try:
            result = validate_volume_path(str(no_write_dir))

            assert result.valid is False
            assert any("escritura" in e for e in result.errors)
            assert any(str(no_write_dir) in e or "no_write" in e for e in result.errors)
        finally:
            # Restaurar permisos para limpieza
            no_write_dir.chmod(0o755)

    def test_path_without_read_and_write_permissions(self, tmp_path):
        """Una ruta sin permisos r/w retorna ambos errores."""
        no_perms_dir = tmp_path / "no_perms"
        no_perms_dir.mkdir()
        # Quitar permisos de lectura y escritura
        no_perms_dir.chmod(0o100)

        try:
            result = validate_volume_path(str(no_perms_dir))

            assert result.valid is False
            assert len(result.errors) == 2
            assert any("lectura" in e for e in result.errors)
            assert any("escritura" in e for e in result.errors)
        finally:
            # Restaurar permisos para limpieza
            no_perms_dir.chmod(0o755)

    def test_returns_validation_result_instance(self, tmp_path):
        """La función retorna una instancia de ValidationResult."""
        result = validate_volume_path(str(tmp_path))
        assert isinstance(result, ValidationResult)

    def test_file_path_field_contains_resolved_path(self, tmp_path):
        """El campo file_path contiene la ruta resuelta."""
        result = validate_volume_path(str(tmp_path))
        assert result.file_path == str(tmp_path.resolve())

    def test_relative_path_is_resolved(self, tmp_path, monkeypatch):
        """Una ruta relativa se resuelve correctamente."""
        monkeypatch.chdir(tmp_path)
        subdir = tmp_path / "data"
        subdir.mkdir()

        result = validate_volume_path("data")

        assert result.valid is True
        assert result.file_path == str(subdir.resolve())

    def test_nonexistent_path_does_not_check_permissions(self):
        """Si la ruta no existe, no se verifican permisos (solo error de existencia)."""
        result = validate_volume_path("/no/existe/esta/ruta")

        assert result.valid is False
        assert len(result.errors) == 1
        assert "no existe" in result.errors[0]
