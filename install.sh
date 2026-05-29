#!/usr/bin/env bash
# install.sh - Script de instalación de Docker Engine y Docker Compose para Raspberry Pi 4 (ARM64)
#
# Uso: sudo ./install.sh
#
# Códigos de salida:
#   0 - Éxito
#   2 - Error de prerequisitos (arquitectura, OS)
#   5 - Error de red (descarga fallida)

set -euo pipefail

# ==============================================================================
# Constantes
# ==============================================================================
readonly EXIT_SUCCESS=0
readonly EXIT_PREREQUISITES=2
readonly EXIT_NETWORK=5

readonly REQUIRED_ARCH="aarch64"
readonly DOCKER_GPG_URL="https://download.docker.com/linux/debian/gpg"
readonly DOCKER_REPO_URL="https://download.docker.com/linux/debian"

# ==============================================================================
# Funciones de utilidad
# ==============================================================================

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    echo "[INFO]  $(timestamp) - install: $1"
}

log_error() {
    echo "[ERROR] $(timestamp) - install: $1" >&2
}

log_warn() {
    echo "[WARN]  $(timestamp) - install: $1" >&2
}

# ==============================================================================
# Verificaciones de prerequisitos
# ==============================================================================

check_architecture() {
    local arch
    arch="$(uname -m)"

    if [[ "$arch" != "$REQUIRED_ARCH" ]]; then
        log_error "Arquitectura no soportada: '$arch'. Se requiere '$REQUIRED_ARCH' (ARM64)."
        log_error "Acción correctiva: Este script solo es compatible con Raspberry Pi 4 con sistema operativo de 64 bits."
        log_error "Verifique que está usando una imagen de 64 bits de Raspberry Pi OS."
        exit $EXIT_PREREQUISITES
    fi

    log_info "Arquitectura verificada: $arch"
}

check_64bit_os() {
    local bitness
    bitness="$(getconf LONG_BIT)"

    if [[ "$bitness" != "64" ]]; then
        log_error "Sistema operativo de 32 bits detectado (${bitness}-bit). Se requiere un OS de 64 bits."
        log_error "Acción correctiva: Instale una versión de 64 bits de Raspberry Pi OS."
        log_error "Descargue la imagen de 64 bits desde: https://www.raspberrypi.com/software/operating-systems/"
        exit $EXIT_PREREQUISITES
    fi

    log_info "Sistema operativo de 64 bits verificado."
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Este script debe ejecutarse como root."
        log_error "Acción correctiva: Ejecute con sudo: sudo ./install.sh"
        exit $EXIT_PREREQUISITES
    fi
}

# ==============================================================================
# Instalación de Docker Engine
# ==============================================================================

install_docker_prerequisites() {
    log_info "Instalando paquetes prerequisitos..."

    if ! apt-get update -y 2>/dev/null; then
        log_error "No se pudo actualizar la lista de paquetes."
        log_error "Acción correctiva: Verifique su conexión a internet y la configuración de DNS."
        log_error "Intente: ping -c 1 download.docker.com"
        exit $EXIT_NETWORK
    fi

    if ! apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release 2>/dev/null; then
        log_error "No se pudieron instalar los paquetes prerequisitos."
        log_error "Acción correctiva: Verifique su conexión a internet y que los repositorios estén accesibles."
        exit $EXIT_NETWORK
    fi

    log_info "Paquetes prerequisitos instalados correctamente."
}

setup_docker_repository() {
    log_info "Configurando repositorio oficial de Docker..."

    # Crear directorio para keyrings si no existe
    install -m 0755 -d /etc/apt/keyrings

    # Descargar y configurar la clave GPG de Docker
    if ! curl -fsSL "$DOCKER_GPG_URL" -o /etc/apt/keyrings/docker.asc 2>/dev/null; then
        log_error "No se pudo descargar la clave GPG de Docker desde: $DOCKER_GPG_URL"
        log_error "Acción correctiva: Verifique su conexión a internet."
        log_error "Intente: curl -fsSL $DOCKER_GPG_URL"
        exit $EXIT_NETWORK
    fi

    chmod a+r /etc/apt/keyrings/docker.asc

    # Detectar distribución
    local codename
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        # Raspberry Pi OS se basa en Debian, usar VERSION_CODENAME
        codename="${VERSION_CODENAME:-}"
    fi

    if [[ -z "$codename" ]]; then
        log_warn "No se pudo detectar el codename de la distribución. Usando 'bookworm' por defecto."
        codename="bookworm"
    fi

    # Agregar repositorio de Docker
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] $DOCKER_REPO_URL $codename stable" \
        > /etc/apt/sources.list.d/docker.list

    # Actualizar índice de paquetes con el nuevo repositorio
    if ! apt-get update -y 2>/dev/null; then
        log_error "No se pudo actualizar la lista de paquetes después de agregar el repositorio de Docker."
        log_error "Acción correctiva: Verifique que el repositorio es accesible: $DOCKER_REPO_URL"
        exit $EXIT_NETWORK
    fi

    log_info "Repositorio oficial de Docker configurado correctamente."
}

install_docker_engine() {
    log_info "Instalando Docker Engine..."

    if ! apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin 2>/dev/null; then
        log_error "No se pudo instalar Docker Engine."
        log_error "Acción correctiva: Verifique que el repositorio de Docker está correctamente configurado."
        log_error "Intente: apt-cache policy docker-ce"
        exit $EXIT_NETWORK
    fi

    log_info "Docker Engine instalado correctamente."
}

# ==============================================================================
# Configuración post-instalación
# ==============================================================================

enable_docker_systemd() {
    log_info "Habilitando Docker en systemd para inicio automático..."

    if ! systemctl enable docker 2>/dev/null; then
        log_error "No se pudo habilitar Docker en systemd."
        log_error "Acción correctiva: Verifique que systemd está disponible en su sistema."
        log_error "Intente: systemctl status docker"
        exit $EXIT_PREREQUISITES
    fi

    if ! systemctl start docker 2>/dev/null; then
        log_error "No se pudo iniciar el servicio Docker."
        log_error "Acción correctiva: Revise los logs del sistema: journalctl -xeu docker.service"
        exit $EXIT_PREREQUISITES
    fi

    log_info "Docker habilitado e iniciado en systemd."
}

verify_installation() {
    log_info "Verificando instalación..."

    # Verificar Docker Engine
    if ! timeout 30 docker info > /dev/null 2>&1; then
        log_error "Docker Engine no responde después de la instalación."
        log_error "Acción correctiva: Revise el estado del servicio: systemctl status docker"
        log_error "Revise los logs: journalctl -xeu docker.service"
        exit $EXIT_PREREQUISITES
    fi

    log_info "Docker Engine está activo y responde correctamente."

    # Verificar Docker Compose
    if ! timeout 10 docker compose version > /dev/null 2>&1; then
        log_error "Docker Compose no está disponible después de la instalación."
        log_error "Acción correctiva: Intente reinstalar el plugin: apt-get install -y docker-compose-plugin"
        exit $EXIT_PREREQUISITES
    fi

    local compose_version
    compose_version="$(docker compose version --short 2>/dev/null || echo 'desconocida')"
    log_info "Docker Compose versión: $compose_version"

    log_info "Verificación post-instalación completada exitosamente."
}

# ==============================================================================
# Función principal
# ==============================================================================

main() {
    log_info "Iniciando instalación de Docker para Raspberry Pi 4 (ARM64)..."
    echo "============================================================"

    # Verificar prerequisitos
    check_root
    check_architecture
    check_64bit_os

    # Instalar Docker Engine
    install_docker_prerequisites
    setup_docker_repository
    install_docker_engine

    # Configuración post-instalación
    enable_docker_systemd
    verify_installation

    echo "============================================================"
    log_info "Instalación completada exitosamente."
    log_info "Docker Engine y Docker Compose están listos para usar."
    log_info "Ejecute './verify.sh' para una verificación detallada."

    exit $EXIT_SUCCESS
}

# Ejecutar función principal
main "$@"
