"""Tests unitarios para el validador de configuración."""

import tempfile
from pathlib import Path

import pytest
import yaml

from monitor.config_validator import ConfigValidator, SecurityWarning


@pytest.fixture
def validator():
    """Instancia de ConfigValidator para los tests."""
    return ConfigValidator()


class TestValidateComposeFile:
    """Tests para validate_compose_file."""

    def test_valid_compose_file(self, validator, tmp_path):
        """Un archivo docker-compose válido retorna resultado sin errores."""
        compose = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "ports": ["127.0.0.1:8080:80"],
                }
            },
            "networks": {
                "internal": {"driver": "bridge"}
            },
        }
        f = tmp_path / "docker-compose.yml"
        f.write_text(yaml.dump(compose))

        result = validator.validate_compose_file(str(f))

        assert result.valid is True
        assert result.errors == []

    def test_nonexistent_file(self, validator):
        """Archivo inexistente retorna error."""
        result = validator.validate_compose_file("/no/existe.yml")

        assert result.valid is False
        assert any("no encontrado" in e for e in result.errors)

    def test_invalid_yaml_syntax(self, validator, tmp_path):
        """YAML con sintaxis inválida retorna error con línea."""
        f = tmp_path / "docker-compose.yml"
        f.write_text("services:\n  web:\n    image: [unclosed")

        result = validator.validate_compose_file(str(f))

        assert result.valid is False
        assert any("sintaxis YAML" in e for e in result.errors)

    def test_empty_file_is_valid_with_warning(self, validator, tmp_path):
        """Archivo vacío es válido pero genera advertencia."""
        f = tmp_path / "docker-compose.yml"
        f.write_text("")

        result = validator.validate_compose_file(str(f))

        assert result.valid is True
        assert any("vacío" in w for w in result.warnings)

    def test_non_dict_content_is_invalid(self, validator, tmp_path):
        """Contenido que no es un mapeo es inválido."""
        f = tmp_path / "docker-compose.yml"
        f.write_text("- item1\n- item2")

        result = validator.validate_compose_file(str(f))

        assert result.valid is False
        assert any("mapeo YAML" in e for e in result.errors)

    def test_unrecognized_top_level_key_warns(self, validator, tmp_path):
        """Clave de nivel superior no reconocida genera advertencia."""
        compose = {
            "services": {"web": {"image": "nginx:1.25"}},
            "unknown_key": "value",
        }
        f = tmp_path / "docker-compose.yml"
        f.write_text(yaml.dump(compose))

        result = validator.validate_compose_file(str(f))

        assert result.valid is True
        assert any("unknown_key" in w for w in result.warnings)

    def test_services_not_dict_is_invalid(self, validator, tmp_path):
        """Sección services que no es un mapeo es inválida."""
        f = tmp_path / "docker-compose.yml"
        f.write_text("services:\n  - web\n  - db")

        result = validator.validate_compose_file(str(f))

        assert result.valid is False
        assert any("'services' debe ser un mapeo" in e for e in result.errors)

    def test_reports_multiple_errors(self, validator, tmp_path):
        """Reporta múltiples errores sin detenerse en el primero."""
        compose = {
            "services": {
                "web": None,
                "db": "invalid",
            },
        }
        f = tmp_path / "docker-compose.yml"
        f.write_text(yaml.dump(compose))

        result = validator.validate_compose_file(str(f))

        # Debe reportar problemas para ambos servicios
        assert len(result.errors) + len(result.warnings) >= 2


class TestValidateEnvFile:
    """Tests para validate_env_file."""

    def test_valid_env_file(self, validator, tmp_path):
        """Archivo .env válido retorna resultado sin errores."""
        f = tmp_path / ".env"
        f.write_text("KEY=value\nANOTHER_KEY=123\n")

        result = validator.validate_env_file(str(f))

        assert result.valid is True
        assert result.errors == []

    def test_comments_and_empty_lines_are_valid(self, validator, tmp_path):
        """Comentarios y líneas vacías son válidos."""
        f = tmp_path / ".env"
        f.write_text("# Comentario\n\nKEY=value\n\n# Otro comentario\n")

        result = validator.validate_env_file(str(f))

        assert result.valid is True
        assert result.errors == []

    def test_invalid_format_reports_error(self, validator, tmp_path):
        """Línea con formato inválido reporta error con número de línea."""
        f = tmp_path / ".env"
        f.write_text("KEY=value\ninvalid line without equals\nKEY2=val")

        result = validator.validate_env_file(str(f))

        assert result.valid is False
        assert any("línea 2" in e for e in result.errors)
        assert any("formato inválido" in e for e in result.errors)

    def test_empty_value_warns(self, validator, tmp_path):
        """Variable con valor vacío genera advertencia."""
        f = tmp_path / ".env"
        f.write_text("KEY=\nANOTHER=value\n")

        result = validator.validate_env_file(str(f))

        assert result.valid is True
        assert any("valor vacío" in w for w in result.warnings)
        assert any("KEY" in w for w in result.warnings)

    def test_nonexistent_file(self, validator):
        """Archivo inexistente retorna error."""
        result = validator.validate_env_file("/no/existe/.env")

        assert result.valid is False
        assert any("no encontrado" in e for e in result.errors)

    def test_multiple_invalid_lines(self, validator, tmp_path):
        """Reporta errores para múltiples líneas inválidas."""
        f = tmp_path / ".env"
        f.write_text("bad line 1\nKEY=ok\n123invalid\n")

        result = validator.validate_env_file(str(f))

        assert result.valid is False
        assert len(result.errors) == 2


class TestValidateServiceConfig:
    """Tests para validate_service_config."""

    def test_valid_service(self, validator, tmp_path):
        """Servicio con configuración completa es válido."""
        svc_dir = tmp_path / "services" / "web"
        svc_dir.mkdir(parents=True)
        compose = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "networks": ["internal"],
                    "ports": ["127.0.0.1:8080:80"],
                    "security_opt": ["no-new-privileges:true"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost/"],
                        "interval": "30s",
                    },
                }
            },
            "networks": {
                "internal": {"external": True, "name": "rpi4_internal"}
            },
        }
        override = svc_dir / "docker-compose.override.yml"
        override.write_text(yaml.dump(compose))

        result = validator.validate_service_config("web", str(tmp_path))

        assert result.valid is True
        assert result.errors == []

    def test_missing_service_directory(self, validator, tmp_path):
        """Directorio de servicio inexistente retorna error."""
        result = validator.validate_service_config("nonexistent", str(tmp_path))

        assert result.valid is False
        assert any("no encontrado" in e for e in result.errors)

    def test_missing_override_file(self, validator, tmp_path):
        """Falta de docker-compose.override.yml retorna error."""
        svc_dir = tmp_path / "services" / "web"
        svc_dir.mkdir(parents=True)

        result = validator.validate_service_config("web", str(tmp_path))

        assert result.valid is False
        assert any("falta docker-compose.override.yml" in e for e in result.errors)

    def test_service_without_image_or_build(self, validator, tmp_path):
        """Servicio sin image ni build retorna error."""
        svc_dir = tmp_path / "services" / "web"
        svc_dir.mkdir(parents=True)
        compose = {
            "services": {
                "web": {
                    "ports": ["127.0.0.1:8080:80"],
                }
            },
        }
        override = svc_dir / "docker-compose.override.yml"
        override.write_text(yaml.dump(compose))

        result = validator.validate_service_config("web", str(tmp_path))

        assert result.valid is False
        assert any("'image' ni 'build'" in e for e in result.errors)


class TestCheckSecurityCompliance:
    """Tests para check_security_compliance."""

    def test_fully_compliant_service(self, validator):
        """Servicio completamente seguro no genera advertencias."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert warnings == []

    def test_missing_user_warns(self, validator):
        """Servicio sin usuario genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("no-root" in w.issue or "user" in w.issue for w in warnings)

    def test_root_user_without_exception_errors(self, validator):
        """Servicio con root sin justificación genera error."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "0",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("root" in w.issue.lower() for w in warnings)

    def test_missing_no_new_privileges_warns(self, validator):
        """Servicio sin no-new-privileges genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("no-new-privileges" in w.issue for w in warnings)

    def test_port_not_localhost_warns(self, validator):
        """Puerto no vinculado a localhost genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("127.0.0.1" in w.issue or "localhost" in w.issue for w in warnings)

    def test_restart_always_warns(self, validator):
        """Política 'always' sin límite genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "always",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("reinicio" in w.issue or "restart" in w.issue.lower() for w in warnings)

    def test_no_resource_limits_warns(self, validator):
        """Servicio sin límites de recursos genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:1.25",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("recursos" in w.issue or "límite" in w.issue for w in warnings)

    def test_image_latest_warns(self, validator):
        """Imagen con tag 'latest' genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("versión" in w.issue or "latest" in w.issue for w in warnings)

    def test_image_without_tag_warns(self, validator):
        """Imagen sin etiqueta genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        assert any("versión" in w.issue or "sin" in w.issue for w in warnings)

    def test_image_with_sha256_is_pinned(self, validator):
        """Imagen con digest sha256 no genera advertencia."""
        config = {
            "services": {
                "web": {
                    "image": "nginx@sha256:abc123def456",
                    "user": "1000:1000",
                    "security_opt": ["no-new-privileges:true"],
                    "ports": ["127.0.0.1:8080:80"],
                    "restart": "on-failure:5",
                    "deploy": {
                        "resources": {
                            "limits": {"cpus": "1.0", "memory": "512M"}
                        }
                    },
                }
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        # No debe haber advertencia de imagen
        assert not any("versión" in w.issue or "imagen" in w.issue for w in warnings)

    def test_multiple_services_all_checked(self, validator):
        """Verifica seguridad de múltiples servicios."""
        config = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "ports": ["8080:80"],
                },
                "db": {
                    "image": "postgres",
                    "ports": ["5432:5432"],
                },
            }
        }

        warnings = validator.check_security_compliance(config, "test.yml")

        # Debe haber advertencias para ambos servicios
        web_warnings = [w for w in warnings if w.service_name == "web"]
        db_warnings = [w for w in warnings if w.service_name == "db"]
        assert len(web_warnings) > 0
        assert len(db_warnings) > 0

    def test_empty_services_no_warnings(self, validator):
        """Configuración sin servicios no genera advertencias."""
        config = {"networks": {"internal": {"driver": "bridge"}}}

        warnings = validator.check_security_compliance(config, "test.yml")

        assert warnings == []


class TestValidateVolumePath:
    """Tests para validate_volume_path."""

    def test_valid_path(self, validator, tmp_path):
        """Ruta válida con permisos retorna resultado exitoso."""
        result = validator.validate_volume_path(str(tmp_path))

        assert result.valid is True
        assert result.errors == []

    def test_nonexistent_path(self, validator):
        """Ruta inexistente retorna error."""
        result = validator.validate_volume_path("/ruta/que/no/existe")

        assert result.valid is False
        assert any("no existe" in e for e in result.errors)

    def test_file_not_directory(self, validator, tmp_path):
        """Ruta que es un archivo (no directorio) retorna error."""
        f = tmp_path / "file.txt"
        f.write_text("content")

        result = validator.validate_volume_path(str(f))

        assert result.valid is False
        assert any("no es un directorio" in e for e in result.errors)
