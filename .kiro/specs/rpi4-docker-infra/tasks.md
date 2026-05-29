# Implementation Plan: rpi4-docker-infra

## Overview

Este plan implementa la infraestructura Docker para Raspberry Pi 4 en tres capas: scripts de instalación (Bash), orquestación (Docker Compose), y monitoreo (Python). Las tareas están organizadas para construir incrementalmente desde la estructura base hasta la integración completa.

## Tasks

- [ ] 1. Configurar estructura del proyecto e interfaces base
  - [x] 1.1 Crear estructura de directorios y archivos de configuración base
    - Crear la estructura de directorios: `services/service-template/`, `monitor/`, `logs/`, `volumes/`, `tests/`
    - Crear `.env.example` con variables documentadas (VOLUMES_PATH, etc.)
    - Crear `.gitignore` que excluya `.env`, `logs/`, `volumes/`
    - Crear `monitor/requirements.txt` con dependencias (docker, pyyaml, hypothesis, pytest)
    - _Requirements: 7.7, 8.1, 8.4_

  - [x] 1.2 Definir modelos de datos Python para el sistema de monitoreo
    - Crear `monitor/models.py` con las dataclasses: `ContainerState`, `MonitorConfig`, `ResourceMetrics`, `HealthStatus`, `Alert`, `ValidationResult`, `DiskStatus`, `RestartResult`, `ServiceSecurityConfig`
    - Implementar enums y valores por defecto según el diseño
    - _Requirements: 6.1, 6.5, 7.2, 7.9_

  - [x] 1.3 Crear archivo de configuración del monitor
    - Crear `monitor/config.yml` con todos los parámetros configurables (intervalos, umbrales, límites)
    - Implementar función de carga de configuración que parsee YAML y retorne `MonitorConfig`
    - _Requirements: 6.1, 6.6, 6.7_

- [x] 2. Implementar capa de instalación (scripts Bash)
  - [x] 2.1 Implementar script de instalación (`install.sh`)
    - Verificar arquitectura ARM64 (`uname -m` == `aarch64`) y OS de 64 bits
    - Instalar Docker Engine desde repositorio oficial
    - Instalar Docker Compose plugin v2
    - Habilitar Docker en systemd (`systemctl enable docker`)
    - Usar `set -euo pipefail` para manejo de errores
    - Implementar códigos de salida (0=éxito, 2=prerequisitos, 5=red)
    - Sugerir acciones correctivas en mensajes de error
    - _Requirements: 1.1, 1.3, 1.4, 1.5_

  - [x] 2.2 Implementar script de verificación (`verify.sh`)
    - Ejecutar `docker info` con timeout de 30 segundos
    - Ejecutar `docker compose version` con timeout de 10 segundos
    - Verificar versión mínima de Docker Compose (>= 2.20.0) con comparación semántica
    - Reportar resultados en stdout con formato de mensajes estándar
    - Implementar códigos de salida apropiados
    - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 2.3 Escribir tests unitarios para comparación de versiones
    - Crear `tests/unit/test_version_compare.py` (o `tests/smoke/test_installation.bats` para Bash)
    - Testear comparación de versiones semánticas con casos borde (2.20.0 vs 2.19.9, 2.20.0 vs 2.20.0)
    - _Requirements: 2.3_

  - [ ]* 2.4 Escribir test de propiedad para comparación de versiones
    - **Property 1: Comparación de versiones**
    - Crear `tests/property/test_prop_version_compare.py`
    - Generar pares de versiones semánticas aleatorias y verificar orden correcto
    - **Validates: Requirements 2.3**

- [x] 3. Implementar capa de orquestación (Docker Compose)
  - [x] 3.1 Crear archivo Docker Compose principal y plantilla de servicio
    - Crear `docker-compose.yml` con definición de red interna (`rpi4_internal`, driver bridge)
    - Crear `services/service-template/docker-compose.override.yml` con todos los parámetros documentados
    - Incluir comentarios descriptivos e instrucciones para agregar nuevos servicios
    - Configurar seguridad por defecto: user non-root, no-new-privileges, puertos en 127.0.0.1, límites de recursos
    - _Requirements: 4.1, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.9, 8.1, 8.4_

  - [x] 3.2 Implementar script de gestión (`manage.sh`)
    - Implementar comandos: `start`, `stop`, `restart <servicio>`, `status`, `validate`, `logs <servicio>`
    - `start`: ejecutar `docker compose up -d` con timeout de 60s por contenedor
    - `stop`: ejecutar `docker compose down` con SIGTERM + 10s grace period
    - `restart`: validar nombre de servicio, reiniciar solo ese contenedor
    - `status`: mostrar tabla con nombre, estado, puertos, uptime
    - `validate`: verificar sintaxis de archivos de configuración
    - `logs`: mostrar últimas 50 líneas del contenedor indicado
    - Manejar servicio inexistente con mensaje de error y lista de servicios válidos
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.2, 8.3, 8.5_

  - [ ]* 3.3 Escribir test de propiedad para orden de dependencias
    - **Property 2: Orden de dependencias (inicio y detención)**
    - Crear `tests/property/test_prop_dependency_order.py`
    - Generar grafos acíclicos dirigidos aleatorios y verificar que el orden de inicio es topológico válido y el de detención es su inverso
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 3.4 Escribir test de propiedad para completitud del estado
    - **Property 3: Completitud del estado de contenedores**
    - Crear `tests/property/test_prop_display_functions.py`
    - Generar metadatos de contenedores aleatorios y verificar que la salida incluye todos los campos requeridos
    - **Validates: Requirements 3.4**

  - [ ]* 3.5 Escribir test de propiedad para error de servicio inexistente
    - **Property 4: Error de servicio inexistente**
    - Crear `tests/property/test_prop_service_error.py`
    - Generar nombres de servicio inexistentes y listas de servicios válidos, verificar que el error contiene el nombre solicitado y lista los válidos
    - **Validates: Requirements 3.6**

- [x] 4. Checkpoint - Verificar estructura base
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implementar validador de configuración
  - [x] 5.1 Implementar validador de configuración (`config_validator.py`)
    - Crear `monitor/config_validator.py` con clase `ConfigValidator`
    - Implementar `validate_compose_file()`: parsear YAML, verificar estructura válida de docker-compose
    - Implementar `validate_env_file()`: verificar formato clave=valor, detectar variables vacías
    - Implementar `validate_service_config()`: verificar configuración completa de un servicio
    - Implementar `check_security_compliance()`: verificar usuario no-root, no-new-privileges, puertos en localhost, política de reinicio, límites de recursos
    - Reportar todos los errores (no detenerse en el primero), indicando archivo y línea
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 7.8, 7.9, 8.5, 8.6_

  - [ ]* 5.2 Escribir test de propiedad para validación de seguridad
    - **Property 12: Cumplimiento de seguridad en configuración**
    - Crear `tests/property/test_prop_security.py`
    - Generar configuraciones de servicio aleatorias y verificar que la validación detecta correctamente violaciones de seguridad
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5, 7.8**

  - [ ]* 5.3 Escribir test de propiedad para resolución de límites de recursos
    - **Property 13: Resolución de límites de recursos**
    - Crear `tests/property/test_prop_resource_limits.py`
    - Generar configuraciones con y sin límites explícitos, verificar que se aplican valores por defecto (1 CPU, 512MB) cuando no hay límites
    - **Validates: Requirements 7.2, 7.9**

  - [ ]* 5.4 Escribir test de propiedad para validación de etiqueta de imagen
    - **Property 14: Validación de etiqueta de imagen**
    - Crear `tests/property/test_prop_image_tags.py`
    - Generar referencias de imagen aleatorias y verificar que se genera advertencia solo para "latest" o sin etiqueta
    - **Validates: Requirements 7.6**

  - [ ]* 5.5 Escribir test de propiedad para validación de configuración con reporte de errores
    - **Property 15: Validación de configuración con reporte de errores**
    - Crear `tests/property/test_prop_config_validator.py`
    - Generar contenido YAML válido e inválido, verificar que se identifican errores de sintaxis con archivo y línea
    - **Validates: Requirements 8.5, 8.6**

- [x] 6. Implementar capa de monitoreo - Monitor de salud
  - [x] 6.1 Implementar monitor de salud (`health-monitor.py`)
    - Crear `monitor/health-monitor.py` con clase `HealthMonitor`
    - Implementar `check_container_health()`: verificar estado del contenedor con timeout de 5s
    - Implementar `check_resource_usage()`: obtener métricas de CPU, memoria y red
    - Implementar `evaluate_alerts()`: evaluar umbrales de memoria (85%) y CPU (90% x 3 ciclos)
    - Implementar `handle_unhealthy()`: reiniciar contenedor con máximo 3 intentos en 5 minutos
    - Implementar máquina de estados: Healthy → CheckFailed → Unhealthy → Restarting → Critical
    - Implementar `run()`: bucle principal cada 30 segundos
    - Implementar manejo de desconexión de Docker: reintentar cada 60s, máximo 10 intentos
    - Configurar logging con rotación (10MB, 3 backups)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [ ]* 6.2 Escribir test de propiedad para máquina de estados del monitor
    - **Property 8: Máquina de estados del monitor de salud**
    - Crear `tests/property/test_prop_health_monitor.py`
    - Generar secuencias aleatorias de resultados de health check y reinicio, verificar transiciones de estado correctas
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [ ]* 6.3 Escribir test de propiedad para alerta de umbral de memoria
    - **Property 9: Alerta de umbral de memoria**
    - Crear `tests/property/test_prop_resource_alerts.py` (parte memoria)
    - Generar valores de uso de memoria aleatorios, verificar que se genera alerta si y solo si supera 85%
    - **Validates: Requirements 6.6**

  - [ ]* 6.4 Escribir test de propiedad para alerta de CPU por ciclos consecutivos
    - **Property 10: Alerta de CPU por ciclos consecutivos**
    - Agregar a `tests/property/test_prop_resource_alerts.py` (parte CPU)
    - Generar secuencias de mediciones de CPU, verificar alerta solo con 3 mediciones consecutivas > 90%
    - **Validates: Requirements 6.7**

  - [ ]* 6.5 Escribir test de propiedad para reconexión a Docker
    - **Property 11: Máquina de estados de reconexión a Docker**
    - Crear `tests/property/test_prop_reconnection.py`
    - Generar secuencias de intentos de conexión, verificar reintentos cada 60s hasta máximo 10 y alerta al agotar
    - **Validates: Requirements 6.8, 6.9**

- [ ] 7. Implementar capa de monitoreo - Monitor de disco y volúmenes
  - [x] 7.1 Implementar monitor de disco (`disk_monitor.py`)
    - Crear `monitor/disk_monitor.py` con clase `DiskMonitor`
    - Implementar `check_disk_space()`: verificar espacio disponible en ruta de volúmenes
    - Implementar `should_notify()`: máximo 1 notificación cada 10 minutos
    - Verificar espacio cada 60 segundos
    - Generar alerta cuando espacio disponible < 10% de capacidad total
    - _Requirements: 5.6_

  - [x] 7.2 Implementar validación de rutas de volúmenes
    - Agregar a `monitor/config_validator.py` o crear función en `manage.sh`
    - Validar que la ruta de volúmenes existe y tiene permisos de lectura/escritura
    - Generar mensaje de error indicando ruta inválida y permiso faltante
    - Impedir inicio de contenedor si la ruta es inválida
    - _Requirements: 5.3, 5.4_

  - [ ]* 7.3 Escribir test de propiedad para umbral de disco y cooldown
    - **Property 7: Umbral de disco y cooldown de notificaciones**
    - Crear `tests/property/test_prop_disk_monitor.py`
    - Generar secuencias de lecturas de disco con timestamps, verificar alerta cuando < 10% y máximo 1 notificación cada 10 min
    - **Validates: Requirements 5.6**

  - [ ]* 7.4 Escribir test de propiedad para validación de ruta de volúmenes
    - **Property 5: Validación de ruta de volúmenes**
    - Crear `tests/property/test_prop_path_validation.py`
    - Generar rutas aleatorias, verificar que se rechazan rutas inexistentes o sin permisos con mensaje apropiado
    - **Validates: Requirements 5.4**

  - [ ]* 7.5 Escribir test de propiedad para completitud de información de volúmenes
    - **Property 6: Completitud de información de volúmenes**
    - Agregar a `tests/property/test_prop_display_functions.py`
    - Generar metadatos de volúmenes aleatorios, verificar que la salida incluye nombre, tamaño en MB y contenedor asociado
    - **Validates: Requirements 5.5**

- [ ] 8. Checkpoint - Verificar monitoreo completo
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integración y conexión de componentes
  - [x] 9.1 Integrar validador con script de gestión
    - Conectar `manage.sh validate` con `config_validator.py`
    - Asegurar que `manage.sh start` ejecuta validación antes de iniciar contenedores
    - Verificar que errores de validación impiden el inicio y muestran archivo/línea
    - _Requirements: 8.5, 8.6_

  - [x] 9.2 Integrar monitor de salud como servicio del sistema
    - Configurar `health-monitor.py` para ejecutarse como proceso de fondo
    - Integrar `disk_monitor.py` en el bucle principal del monitor de salud
    - Asegurar que el monitor se inicia con `manage.sh start` y se detiene con `manage.sh stop`
    - Verificar que los logs se escriben en `logs/health.log` con rotación configurada
    - _Requirements: 6.1, 5.6_

  - [x] 9.3 Crear servicio de ejemplo funcional
    - Crear `services/service-a/docker-compose.override.yml` con un servicio de ejemplo (nginx ARM64)
    - Verificar que el servicio se inicia correctamente con `manage.sh start`
    - Verificar que el monitor detecta el contenedor y reporta su estado
    - Verificar flujo completo: instalación → inicio → monitoreo → detención
    - _Requirements: 8.2, 8.3_

  - [ ]* 9.4 Escribir tests de integración
    - Crear `tests/integration/test_container_lifecycle.py`: ciclo de vida completo de contenedores
    - Crear `tests/integration/test_multi_project.py`: agregar/eliminar servicios sin afectar existentes
    - _Requirements: 3.3, 8.2, 8.3_

- [x] 10. Checkpoint final - Verificar integración completa
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los tests de propiedad validan propiedades universales de corrección definidas en el diseño
- Los tests unitarios validan ejemplos específicos y casos borde
- Los scripts Bash usan `set -euo pipefail` para manejo estricto de errores
- El monitoreo Python usa la librería `docker` para interactuar con Docker Engine
- Los tests de propiedad usan Hypothesis como framework PBT

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1"] },
    { "id": 2, "tasks": ["2.3", "2.4", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5"] },
    { "id": 7, "tasks": ["9.1", "9.2"] },
    { "id": 8, "tasks": ["9.3"] },
    { "id": 9, "tasks": ["9.4"] }
  ]
}
```
