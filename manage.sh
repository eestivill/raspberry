#!/usr/bin/env bash
# =============================================================================
# Script de Gestión de Contenedores - Infraestructura Docker Raspberry Pi 4
# =============================================================================
#
# Proporciona comandos simplificados para gestionar los contenedores Docker.
#
# USO:
#   ./manage.sh start              # Iniciar todos los servicios
#   ./manage.sh stop               # Detener todos los servicios
#   ./manage.sh restart <servicio> # Reiniciar un servicio específico
#   ./manage.sh status             # Mostrar estado de contenedores
#   ./manage.sh validate           # Validar configuración
#   ./manage.sh logs <servicio>    # Mostrar logs de un servicio
#
# CÓDIGOS DE SALIDA:
#   0 - Éxito
#   1 - Error general
#   3 - Error de configuración
#   4 - Error de ejecución (contenedor no inicia, timeout)
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
readonly SERVICES_DIR="${SCRIPT_DIR}/services"
readonly TIMEOUT_PER_CONTAINER=60
readonly STOP_GRACE_PERIOD=10
readonly LOG_TAIL_LINES=50
readonly MONITOR_PID_FILE="${SCRIPT_DIR}/logs/monitor.pid"
readonly MONITOR_LOG_FILE="${SCRIPT_DIR}/logs/health.log"

# -----------------------------------------------------------------------------
# Funciones de utilidad
# -----------------------------------------------------------------------------

# Formato de timestamp para mensajes
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Mensajes con formato estándar
log_info() {
    echo "[INFO]  $(timestamp) - manage: $1"
}

log_error() {
    echo "[ERROR] $(timestamp) - manage: $1" >&2
}

log_warn() {
    echo "[WARN]  $(timestamp) - manage: $1"
}

# Construir la lista de archivos compose (principal + overrides de servicios)
build_compose_files() {
    local compose_args=("-f" "${COMPOSE_FILE}")

    if [[ -d "${SERVICES_DIR}" ]]; then
        for service_dir in "${SERVICES_DIR}"/*/; do
            local override_file="${service_dir}docker-compose.override.yml"
            if [[ -f "${override_file}" ]] && [[ "$(basename "${service_dir}")" != "service-template" ]]; then
                compose_args+=("-f" "${override_file}")
            fi
        done
    fi

    echo "${compose_args[@]}"
}

# Obtener lista de servicios válidos definidos en la configuración
get_valid_services() {
    local compose_args
    compose_args=($(build_compose_files))

    docker compose "${compose_args[@]}" config --services 2>/dev/null || true
}

# Verificar si un servicio existe en la configuración
service_exists() {
    local service_name="$1"
    local valid_services
    valid_services=$(get_valid_services)

    if [[ -z "${valid_services}" ]]; then
        return 1
    fi

    echo "${valid_services}" | grep -qx "${service_name}"
}

# Mostrar error de servicio inexistente con lista de servicios válidos
show_service_not_found_error() {
    local requested_service="$1"
    local valid_services
    valid_services=$(get_valid_services)

    log_error "El servicio '${requested_service}' no fue encontrado en la configuración."

    if [[ -n "${valid_services}" ]]; then
        echo ""
        echo "Servicios válidos disponibles:"
        echo "${valid_services}" | while read -r svc; do
            echo "  - ${svc}"
        done
    else
        echo ""
        echo "No hay servicios definidos en la configuración."
        echo "Para agregar un servicio, copie services/service-template/ a services/<nombre>/"
    fi
}

# -----------------------------------------------------------------------------
# Validación de ruta de volúmenes
# -----------------------------------------------------------------------------
# Verifica que la ruta de volúmenes existe y tiene permisos de lectura/escritura.
# Impide el inicio de contenedores si la ruta es inválida.
validate_volumes_path() {
    local volumes_path="${VOLUMES_PATH:-${SCRIPT_DIR}/volumes}"

    # Usar el validador Python si está disponible
    if command -v python3 &>/dev/null; then
        local validation_output
        validation_output=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from monitor.volume_validator import validate_volume_path
result = validate_volume_path('${volumes_path}')
if not result.valid:
    for error in result.errors:
        print(error, file=sys.stderr)
    sys.exit(1)
" 2>&1)

        if [[ $? -ne 0 ]]; then
            log_error "Validación de ruta de volúmenes fallida:"
            echo "${validation_output}" | while IFS= read -r line; do
                log_error "  ${line}"
            done
            return 1
        fi
    else
        # Fallback: validación básica en Bash
        if [[ ! -d "${volumes_path}" ]]; then
            log_error "La ruta de volúmenes no existe: ${volumes_path}"
            return 1
        fi
        if [[ ! -r "${volumes_path}" ]]; then
            log_error "La ruta de volúmenes no tiene permiso de lectura: ${volumes_path}"
            return 1
        fi
        if [[ ! -w "${volumes_path}" ]]; then
            log_error "La ruta de volúmenes no tiene permiso de escritura: ${volumes_path}"
            return 1
        fi
    fi

    return 0
}

# -----------------------------------------------------------------------------
# Gestión del monitor de salud
# -----------------------------------------------------------------------------

# Inicia el monitor de salud como proceso de fondo.
start_health_monitor() {
    # Verificar si ya está corriendo
    if [[ -f "${MONITOR_PID_FILE}" ]]; then
        local existing_pid
        existing_pid=$(cat "${MONITOR_PID_FILE}")
        if kill -0 "${existing_pid}" 2>/dev/null; then
            log_info "Monitor de salud ya está en ejecución (PID: ${existing_pid})"
            return 0
        else
            # PID file obsoleto, eliminarlo
            rm -f "${MONITOR_PID_FILE}"
        fi
    fi

    # Crear directorio de logs si no existe
    mkdir -p "${SCRIPT_DIR}/logs"

    # Iniciar el monitor como proceso de fondo
    if command -v python3 &>/dev/null; then
        cd "${SCRIPT_DIR}"
        python3 -m monitor.health_monitor --pid-file "${MONITOR_PID_FILE}" &
        local monitor_pid=$!
        disown "${monitor_pid}"
        log_info "Monitor de salud iniciado (PID: ${monitor_pid})"
    else
        log_warn "Python3 no disponible. Monitor de salud no iniciado."
    fi
}

# Detiene el monitor de salud.
stop_health_monitor() {
    if [[ ! -f "${MONITOR_PID_FILE}" ]]; then
        log_info "Monitor de salud no está en ejecución (no se encontró archivo PID)"
        return 0
    fi

    local pid
    pid=$(cat "${MONITOR_PID_FILE}")

    if kill -0 "${pid}" 2>/dev/null; then
        log_info "Deteniendo monitor de salud (PID: ${pid})..."
        kill -TERM "${pid}" 2>/dev/null || true

        # Esperar a que el proceso termine (máximo 10 segundos)
        local wait_count=0
        while kill -0 "${pid}" 2>/dev/null && [[ ${wait_count} -lt 10 ]]; do
            sleep 1
            wait_count=$((wait_count + 1))
        done

        if kill -0 "${pid}" 2>/dev/null; then
            log_warn "Monitor de salud no respondió a SIGTERM, enviando SIGKILL..."
            kill -KILL "${pid}" 2>/dev/null || true
        fi

        log_info "Monitor de salud detenido."
    else
        log_info "Monitor de salud no está en ejecución (proceso ${pid} no encontrado)"
    fi

    # Limpiar archivo PID
    rm -f "${MONITOR_PID_FILE}"
}

# -----------------------------------------------------------------------------
# Comando: start
# -----------------------------------------------------------------------------
# Inicia todos los contenedores definidos en la configuración.
# Ejecuta validación de configuración antes de iniciar.
# Espera un máximo de 60 segundos por contenedor para alcanzar estado operativo.
cmd_start() {
    log_info "Iniciando todos los servicios..."

    # Validar ruta de volúmenes antes de iniciar
    if ! validate_volumes_path; then
        log_error "No se pueden iniciar los contenedores: ruta de volúmenes inválida."
        exit 3
    fi

    # Validar configuración antes de iniciar contenedores
    log_info "Ejecutando validación de configuración antes de iniciar..."
    if command -v python3 &>/dev/null; then
        local validator_output
        local validator_exit=0
        validator_output=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from monitor.config_validator import run_validation
sys.exit(run_validation('${SCRIPT_DIR}'))
" 2>&1) || validator_exit=$?

        if [[ ${validator_exit} -ne 0 ]]; then
            log_error "Validación de configuración fallida. No se iniciarán los contenedores."
            echo "${validator_output}" | while IFS= read -r line; do
                if [[ -n "${line}" ]]; then
                    echo "  ${line}" >&2
                fi
            done
            log_error "Corrija los errores indicados (archivo/línea) y vuelva a intentar."
            exit 3
        fi
    fi

    local compose_args
    compose_args=($(build_compose_files))

    if ! docker compose "${compose_args[@]}" up -d --timeout "${TIMEOUT_PER_CONTAINER}" 2>&1; then
        log_error "Fallo al iniciar los servicios."

        # Mostrar logs de contenedores que fallaron
        local failed_containers
        failed_containers=$(docker compose "${compose_args[@]}" ps --filter "status=exited" --format "{{.Name}}" 2>/dev/null || true)

        if [[ -n "${failed_containers}" ]]; then
            echo ""
            log_error "Contenedores con fallo durante el inicio:"
            echo "${failed_containers}" | while read -r container; do
                echo ""
                echo "--- Últimos ${LOG_TAIL_LINES} registros de ${container} ---"
                docker logs --tail "${LOG_TAIL_LINES}" "${container}" 2>&1 || true
            done
        fi

        exit 4
    fi

    log_info "Todos los servicios iniciados correctamente."

    # Iniciar monitor de salud como proceso de fondo
    start_health_monitor
}

# -----------------------------------------------------------------------------
# Comando: stop
# -----------------------------------------------------------------------------
# Detiene todos los contenedores enviando SIGTERM con grace period de 10s.
cmd_stop() {
    log_info "Deteniendo todos los servicios (grace period: ${STOP_GRACE_PERIOD}s)..."

    # Detener monitor de salud primero
    stop_health_monitor

    local compose_args
    compose_args=($(build_compose_files))

    if ! docker compose "${compose_args[@]}" down --timeout "${STOP_GRACE_PERIOD}" 2>&1; then
        log_error "Fallo al detener los servicios."
        exit 4
    fi

    log_info "Todos los servicios detenidos correctamente."
}

# -----------------------------------------------------------------------------
# Comando: restart <servicio>
# -----------------------------------------------------------------------------
# Reinicia únicamente el contenedor del servicio indicado.
cmd_restart() {
    local service_name="${1:-}"

    if [[ -z "${service_name}" ]]; then
        log_error "Debe especificar el nombre del servicio a reiniciar."
        echo ""
        echo "Uso: ./manage.sh restart <servicio>"
        exit 1
    fi

    # Validar que el servicio existe
    if ! service_exists "${service_name}"; then
        show_service_not_found_error "${service_name}"
        exit 3
    fi

    log_info "Reiniciando servicio '${service_name}'..."

    local compose_args
    compose_args=($(build_compose_files))

    if ! docker compose "${compose_args[@]}" restart --timeout "${STOP_GRACE_PERIOD}" "${service_name}" 2>&1; then
        log_error "Fallo al reiniciar el servicio '${service_name}'."
        exit 4
    fi

    log_info "Servicio '${service_name}' reiniciado correctamente."
}

# -----------------------------------------------------------------------------
# Comando: status
# -----------------------------------------------------------------------------
# Muestra tabla con nombre, estado, puertos expuestos y tiempo de actividad.
cmd_status() {
    local compose_args
    compose_args=($(build_compose_files))

    # Encabezado de la tabla
    printf "%-25s %-15s %-30s %-20s\n" "NOMBRE" "ESTADO" "PUERTOS" "UPTIME"
    printf "%-25s %-15s %-30s %-20s\n" "-------------------------" "---------------" "------------------------------" "--------------------"

    # Obtener información de contenedores
    local containers
    containers=$(docker compose "${compose_args[@]}" ps --format "{{.Name}}\t{{.State}}\t{{.Ports}}\t{{.Status}}" 2>/dev/null || true)

    if [[ -z "${containers}" ]]; then
        echo ""
        log_info "No hay contenedores en ejecución."
        return 0
    fi

    echo "${containers}" | while IFS=$'\t' read -r name state ports status; do
        # Extraer uptime del campo status (e.g., "Up 2 hours" -> "2 hours")
        local uptime
        uptime=$(echo "${status}" | sed -n 's/^Up \(.*\)/\1/p')
        if [[ -z "${uptime}" ]]; then
            uptime="${status}"
        fi

        # Truncar puertos si son muy largos
        if [[ ${#ports} -gt 28 ]]; then
            ports="${ports:0:25}..."
        fi

        printf "%-25s %-15s %-30s %-20s\n" "${name}" "${state}" "${ports}" "${uptime}"
    done
}

# -----------------------------------------------------------------------------
# Comando: validate
# -----------------------------------------------------------------------------
# Verifica la sintaxis de todos los archivos de configuración.
# Ejecuta validación con docker compose config y luego validación profunda
# con config_validator.py (seguridad, etiquetas de imagen, límites de recursos).
cmd_validate() {
    log_info "Validando archivos de configuración..."

    local has_errors=0

    # Validar archivo principal docker-compose.yml
    if [[ ! -f "${COMPOSE_FILE}" ]]; then
        log_error "Archivo principal no encontrado: ${COMPOSE_FILE}"
        exit 3
    fi

    # Construir lista de archivos compose
    local compose_args
    compose_args=($(build_compose_files))

    # Fase 1: Validar sintaxis con docker compose config
    local validation_output
    if ! validation_output=$(docker compose "${compose_args[@]}" config --quiet 2>&1); then
        log_error "Error de validación en la configuración de Docker Compose:"
        echo "${validation_output}" >&2
        has_errors=1
    fi

    # Validar archivos override individuales
    if [[ -d "${SERVICES_DIR}" ]]; then
        for service_dir in "${SERVICES_DIR}"/*/; do
            local override_file="${service_dir}docker-compose.override.yml"
            if [[ -f "${override_file}" ]] && [[ "$(basename "${service_dir}")" != "service-template" ]]; then
                if ! docker compose -f "${COMPOSE_FILE}" -f "${override_file}" config --quiet 2>&1; then
                    log_error "Error de validación en: ${override_file}"
                    has_errors=1
                fi
            fi
        done
    fi

    # Validar archivo .env si existe (validación básica Bash)
    if [[ -f "${SCRIPT_DIR}/.env" ]]; then
        local line_num=0
        while IFS= read -r line || [[ -n "${line}" ]]; do
            line_num=$((line_num + 1))
            # Ignorar líneas vacías y comentarios
            if [[ -z "${line}" ]] || [[ "${line}" =~ ^[[:space:]]*# ]]; then
                continue
            fi
            # Verificar formato clave=valor
            if ! [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
                log_error "Formato inválido en .env línea ${line_num}: ${line}"
                has_errors=1
            fi
        done < "${SCRIPT_DIR}/.env"
    fi

    # Fase 2: Validación profunda con config_validator.py
    # (seguridad, etiquetas de imagen, límites de recursos, archivo/línea)
    if command -v python3 &>/dev/null; then
        local validator_output
        local validator_exit=0
        validator_output=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from monitor.config_validator import run_validation
sys.exit(run_validation('${SCRIPT_DIR}'))
" 2>&1) || validator_exit=$?

        if [[ ${validator_exit} -ne 0 ]]; then
            log_error "Validación profunda (seguridad/configuración) encontró errores:"
            echo "${validator_output}" | while IFS= read -r line; do
                if [[ -n "${line}" ]]; then
                    echo "  ${line}" >&2
                fi
            done
            has_errors=1
        else
            # Mostrar advertencias si las hay
            if [[ -n "${validator_output}" ]]; then
                echo "${validator_output}" | while IFS= read -r line; do
                    if [[ -n "${line}" ]]; then
                        echo "  ${line}"
                    fi
                done
            fi
        fi
    else
        log_warn "Python3 no disponible: se omite validación profunda de seguridad."
    fi

    if [[ ${has_errors} -eq 1 ]]; then
        log_error "La validación encontró errores. Corrija los problemas antes de aplicar cambios."
        exit 3
    fi

    log_info "Validación completada sin errores."
}

# -----------------------------------------------------------------------------
# Comando: logs <servicio>
# -----------------------------------------------------------------------------
# Muestra las últimas 50 líneas del contenedor indicado.
cmd_logs() {
    local service_name="${1:-}"

    if [[ -z "${service_name}" ]]; then
        log_error "Debe especificar el nombre del servicio."
        echo ""
        echo "Uso: ./manage.sh logs <servicio>"
        exit 1
    fi

    # Validar que el servicio existe
    if ! service_exists "${service_name}"; then
        show_service_not_found_error "${service_name}"
        exit 3
    fi

    local compose_args
    compose_args=($(build_compose_files))

    docker compose "${compose_args[@]}" logs --tail "${LOG_TAIL_LINES}" "${service_name}" 2>&1
}

# -----------------------------------------------------------------------------
# Mostrar ayuda
# -----------------------------------------------------------------------------
show_help() {
    cat << 'EOF'
Gestión de Contenedores - Infraestructura Docker Raspberry Pi 4

Uso: ./manage.sh <comando> [argumentos]

Comandos disponibles:
  start              Iniciar todos los servicios
  stop               Detener todos los servicios
  restart <servicio> Reiniciar un servicio específico
  status             Mostrar estado de contenedores
  validate           Validar archivos de configuración
  logs <servicio>    Mostrar últimas 50 líneas de logs de un servicio

Ejemplos:
  ./manage.sh start
  ./manage.sh restart mi-servicio
  ./manage.sh logs mi-servicio
  ./manage.sh status

Para más información, consulte la documentación del proyecto.
EOF
}

# -----------------------------------------------------------------------------
# Punto de entrada principal
# -----------------------------------------------------------------------------
main() {
    local command="${1:-}"

    if [[ -z "${command}" ]]; then
        log_error "Debe especificar un comando."
        echo ""
        show_help
        exit 1
    fi

    case "${command}" in
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart "${2:-}"
            ;;
        status)
            cmd_status
            ;;
        validate)
            cmd_validate
            ;;
        logs)
            cmd_logs "${2:-}"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Comando desconocido: '${command}'"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
