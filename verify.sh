#!/usr/bin/env bash
# verify.sh - Script de verificación de Docker Engine y Docker Compose
# Verifica que Docker Engine y Docker Compose están correctamente instalados y operativos.
# Entrada: ninguna
# Salida: código de salida 0 (éxito) o distinto de 0 (error)
# Efectos: ninguno (solo lectura)

set -euo pipefail

# --- Constantes ---
readonly DOCKER_INFO_TIMEOUT=30
readonly COMPOSE_VERSION_TIMEOUT=10
readonly MIN_COMPOSE_VERSION="2.20.0"

# --- Códigos de salida ---
# 0 = Éxito
# 2 = Error de prerequisitos (Docker no instalado, no responde)
# 4 = Error de ejecución (timeout, versión insuficiente)

# --- Funciones de formato de mensajes ---
log_info() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[INFO]  ${timestamp} - verify: $1"
}

log_error() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[ERROR] ${timestamp} - verify: $1"
}

log_warn() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[WARN]  ${timestamp} - verify: $1"
}

# --- Comparación de versiones semánticas ---
# Retorna 0 si version_a >= version_b, 1 en caso contrario
version_gte() {
    local version_a="$1"
    local version_b="$2"

    local major_a minor_a patch_a
    local major_b minor_b patch_b

    IFS='.' read -r major_a minor_a patch_a <<< "$version_a"
    IFS='.' read -r major_b minor_b patch_b <<< "$version_b"

    # Eliminar posibles sufijos (e.g., -beta, -rc1)
    patch_a="${patch_a%%[-+]*}"
    patch_b="${patch_b%%[-+]*}"

    # Asegurar valores numéricos
    major_a="${major_a:-0}"
    minor_a="${minor_a:-0}"
    patch_a="${patch_a:-0}"
    major_b="${major_b:-0}"
    minor_b="${minor_b:-0}"
    patch_b="${patch_b:-0}"

    if (( major_a > major_b )); then
        return 0
    elif (( major_a < major_b )); then
        return 1
    fi

    if (( minor_a > minor_b )); then
        return 0
    elif (( minor_a < minor_b )); then
        return 1
    fi

    if (( patch_a >= patch_b )); then
        return 0
    else
        return 1
    fi
}

# --- Verificación de Docker Engine ---
verify_docker_engine() {
    log_info "Verificando Docker Engine..."

    # Verificar que el comando docker existe
    if ! command -v docker &>/dev/null; then
        log_error "Docker Engine no está instalado. Instale Docker primero ejecutando ./install.sh"
        return 2
    fi

    # Ejecutar docker info con timeout
    local docker_info_output
    if ! docker_info_output=$(timeout "${DOCKER_INFO_TIMEOUT}" docker info 2>&1); then
        local exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            log_error "Docker Engine no respondió en ${DOCKER_INFO_TIMEOUT} segundos (timeout)"
            log_error "Sugerencia: Verifique que el servicio Docker está activo con 'systemctl status docker'"
            return 4
        else
            log_error "Docker Engine no está operativo (código de salida: ${exit_code})"
            log_error "Detalle: ${docker_info_output}"
            log_error "Sugerencia: Verifique que el servicio Docker está activo con 'systemctl status docker'"
            log_error "Sugerencia: Verifique que su usuario pertenece al grupo 'docker' o ejecute con sudo"
            return 2
        fi
    fi

    log_info "Docker Engine está activo y operativo"
    return 0
}

# --- Verificación de Docker Compose ---
verify_docker_compose() {
    log_info "Verificando Docker Compose..."

    # Ejecutar docker compose version con timeout
    local compose_version_output
    if ! compose_version_output=$(timeout "${COMPOSE_VERSION_TIMEOUT}" docker compose version 2>&1); then
        local exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            log_error "Docker Compose no respondió en ${COMPOSE_VERSION_TIMEOUT} segundos (timeout)"
            return 4
        else
            log_error "Docker Compose no está instalado o no es accesible"
            log_error "Detalle: ${compose_version_output}"
            log_error "Sugerencia: Instale Docker Compose ejecutando ./install.sh"
            return 2
        fi
    fi

    # Extraer versión de la salida (formato: "Docker Compose version vX.Y.Z")
    local compose_version
    compose_version=$(echo "$compose_version_output" | grep -oP '(\d+\.\d+\.\d+)' | head -1)

    if [[ -z "$compose_version" ]]; then
        log_error "No se pudo determinar la versión de Docker Compose"
        log_error "Salida recibida: ${compose_version_output}"
        return 4
    fi

    log_info "Docker Compose versión detectada: ${compose_version}"

    # Verificar versión mínima
    if ! version_gte "$compose_version" "$MIN_COMPOSE_VERSION"; then
        log_error "La versión de Docker Compose (${compose_version}) es inferior a la mínima requerida (${MIN_COMPOSE_VERSION})"
        log_error "Sugerencia: Actualice Docker Compose ejecutando ./install.sh"
        return 4
    fi

    log_info "Docker Compose versión ${compose_version} cumple con el mínimo requerido (>= ${MIN_COMPOSE_VERSION})"
    return 0
}

# --- Ejecución principal ---
main() {
    log_info "Iniciando verificación de infraestructura Docker..."
    echo ""

    local errors=0

    # Verificar Docker Engine
    if ! verify_docker_engine; then
        errors=$?
    fi

    echo ""

    # Verificar Docker Compose (solo si Docker Engine está disponible)
    if [[ $errors -eq 0 ]]; then
        if ! verify_docker_compose; then
            errors=$?
        fi
    else
        log_warn "Omitiendo verificación de Docker Compose porque Docker Engine no está disponible"
    fi

    echo ""

    # Resumen final
    if [[ $errors -eq 0 ]]; then
        log_info "✓ Verificación completada exitosamente. Docker Engine y Docker Compose están operativos."
        exit 0
    else
        log_error "✗ Verificación fallida. Revise los errores anteriores."
        exit "$errors"
    fi
}

main "$@"
