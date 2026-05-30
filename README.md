# Infraestructura Docker para Raspberry Pi 4

Infraestructura completa para ejecutar múltiples proyectos como contenedores Docker aislados en una Raspberry Pi 4 (ARM64).

## Características

- Instalación automatizada de Docker Engine y Docker Compose para ARM64
- Gestión simplificada de contenedores (start/stop/restart/status)
- Red interna con DNS automático entre servicios
- Almacenamiento persistente con volúmenes configurables
- Monitor de salud con reinicio automático y alertas
- Monitor de disco con notificaciones de espacio bajo
- Validación de configuración y seguridad
- Estructura modular para agregar/quitar proyectos fácilmente

## Requisitos

- Raspberry Pi 4 con sistema operativo de 64 bits (Raspberry Pi OS Lite 64-bit recomendado)
- Conexión a internet (para la instalación inicial)
- Al menos 2GB de RAM (4GB recomendado)
- Tarjeta SD de al menos 16GB (32GB recomendado)

## Instalación rápida

### 1. Clonar el repositorio en la Raspberry Pi

```bash
git clone https://github.com/eestivill/raspberry.git
cd raspberry
chmod +x install.sh verify.sh manage.sh
```

### 2. Instalar Docker

```bash
./install.sh
```

Este script:
- Verifica que el sistema es ARM64 de 64 bits
- Instala Docker Engine desde el repositorio oficial
- Instala Docker Compose (plugin v2, versión >= 2.20.0)
- Habilita Docker para iniciar con el sistema (systemd)

### 3. Verificar la instalación

```bash
./verify.sh
```

Comprueba que Docker Engine y Docker Compose están operativos.

### 4. Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Variables disponibles:
- `VOLUMES_PATH` — Ruta donde se almacenan los datos persistentes (por defecto: `./volumes`)

### 5. Iniciar los servicios

```bash
./manage.sh start
```

## Uso diario

### Comandos disponibles

```bash
./manage.sh start              # Iniciar todos los servicios
./manage.sh stop               # Detener todos los servicios
./manage.sh restart <servicio> # Reiniciar un servicio específico
./manage.sh status             # Ver estado de los contenedores
./manage.sh validate           # Validar la configuración
./manage.sh logs <servicio>    # Ver últimas 50 líneas de logs
```

### Ver el estado

```bash
./manage.sh status
```

Muestra una tabla con nombre, estado, puertos expuestos y tiempo de actividad de cada contenedor.

### Ver logs de un servicio

```bash
./manage.sh logs service-a
```

### Reiniciar un servicio sin afectar los demás

```bash
./manage.sh restart service-a
```

## Agregar un nuevo servicio

### 1. Copiar la plantilla

```bash
cp -r services/service-template services/mi-servicio
```

### 2. Editar la configuración

```bash
nano services/mi-servicio/docker-compose.override.yml
```

Ejemplo para un servicio de base de datos:

```yaml
services:
  mi-base-datos:
    image: postgres:16-alpine
    user: "999:999"
    networks:
      - internal
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - ${VOLUMES_PATH:-./volumes}/mi-base-datos:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
    security_opt:
      - no-new-privileges:true
    restart: on-failure:5
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    env_file:
      - ../../.env

networks:
  internal:
    external: true
    name: rpi4_internal
```

### 3. Validar y arrancar

```bash
./manage.sh validate
./manage.sh start
```

### 4. Verificar que funciona

```bash
./manage.sh status
./manage.sh logs mi-base-datos
```

## Eliminar un servicio

```bash
./manage.sh stop                          # Detener todo
rm -rf services/mi-servicio               # Eliminar configuración
./manage.sh start                         # Reiniciar sin ese servicio
# Los datos en volumes/mi-servicio se preservan por seguridad
```

Para eliminar también los datos:
```bash
rm -rf volumes/mi-servicio
```

## Monitoreo

El sistema incluye un monitor de salud que se ejecuta automáticamente al iniciar los servicios.

### Qué monitorea

- **Salud de contenedores**: Verifica cada 30 segundos que cada contenedor responde
- **Reinicio automático**: Si un contenedor falla 3 veces consecutivas, lo reinicia (máximo 3 intentos en 5 minutos)
- **Uso de memoria**: Alerta cuando un contenedor supera el 85% de su límite
- **Uso de CPU**: Alerta cuando un contenedor supera el 90% durante 3 ciclos consecutivos
- **Espacio en disco**: Alerta cuando queda menos del 10% de espacio disponible

### Ver logs del monitor

```bash
cat logs/health.log
```

### Configuración del monitor

Editar `monitor/config.yml` para ajustar umbrales y intervalos:

```yaml
monitor:
  check_interval: 30        # segundos entre verificaciones
  health_check_timeout: 5   # timeout por intento
  max_failures: 3           # fallos antes de reiniciar
  max_restarts: 3           # reintentos máximos

alerts:
  memory_threshold: 85      # % de memoria para alertar
  cpu_threshold: 90         # % de CPU para alertar
  disk_low_threshold: 10    # % de disco libre mínimo
```

## Seguridad

La infraestructura aplica estas prácticas por defecto:

| Medida | Descripción |
|--------|-------------|
| Usuario no-root | Todos los contenedores corren con usuario sin privilegios |
| Sin escalación | `no-new-privileges` habilitado en todos los contenedores |
| Puertos locales | Los puertos se vinculan a `127.0.0.1` (no accesibles desde fuera) |
| Límites de recursos | CPU y memoria limitados por contenedor (defecto: 1 CPU, 512MB) |
| Reinicio controlado | Máximo 5 reintentos para evitar bucles |
| Secretos separados | Credenciales en `.env` excluido de git |
| Versiones fijas | Advertencia si una imagen usa `latest` |

### Exponer un servicio a la red local

Si necesitas que un servicio sea accesible desde otros dispositivos de tu red:

```yaml
ports:
  - "0.0.0.0:8080:8080"  # Accesible desde la red local
```

## Estructura del proyecto

```
raspberry/
├── install.sh                          # Instalación de Docker
├── verify.sh                           # Verificación post-instalación
├── manage.sh                           # Gestión de contenedores
├── docker-compose.yml                  # Configuración base (red interna)
├── .env.example                        # Plantilla de variables
├── .env                                # Variables reales (no en git)
├── .gitignore
├── services/
│   ├── service-template/               # Plantilla para nuevos servicios
│   │   └── docker-compose.override.yml
│   └── service-a/                      # Servicio de ejemplo (nginx)
│       └── docker-compose.override.yml
├── monitor/
│   ├── health_monitor.py               # Monitor de salud principal
│   ├── disk_monitor.py                 # Monitor de espacio en disco
│   ├── config_validator.py             # Validador de configuración
│   ├── volume_validator.py             # Validador de rutas de volúmenes
│   ├── models.py                       # Modelos de datos
│   ├── config_loader.py                # Carga de configuración
│   ├── config.yml                      # Configuración del monitor
│   └── requirements.txt                # Dependencias Python
├── volumes/                            # Datos persistentes
├── logs/                               # Logs del monitor
└── tests/                              # Suite de tests
```

## Comunicación entre servicios

Los contenedores se comunican entre sí usando el nombre del servicio como dirección DNS:

```bash
# Desde dentro de un contenedor, puedes acceder a otro servicio por nombre:
curl http://service-a:8080
ping mi-base-datos
```

Esto funciona automáticamente gracias a la red interna `rpi4_internal`.

## Actualizar la infraestructura

```bash
cd ~/raspberry
git pull
./manage.sh validate
./manage.sh stop
./manage.sh start
```

## Solución de problemas

### Un contenedor no arranca

```bash
./manage.sh logs mi-servicio
```

### La validación falla

```bash
./manage.sh validate
# Muestra el archivo y línea con el error
```

### Ver el uso de recursos

```bash
docker stats
```

### Reiniciar todo desde cero

```bash
./manage.sh stop
docker system prune -a    # Elimina imágenes y contenedores no usados
./manage.sh start
```

### El monitor no detecta un contenedor

Verifica que el contenedor tiene un `healthcheck` definido en su configuración.

## Desarrollo local (en tu Mac)

Puedes desarrollar y testear la lógica del monitor localmente:

```bash
# Instalar dependencias
pip install -r monitor/requirements.txt

# Ejecutar tests
python -m pytest tests/ -v

# Verificar sintaxis de scripts
bash -n install.sh verify.sh manage.sh
```

Los scripts de instalación (`install.sh`) solo funcionarán en la Raspberry Pi (requieren ARM64).

## Licencia

Uso personal / doméstico.
