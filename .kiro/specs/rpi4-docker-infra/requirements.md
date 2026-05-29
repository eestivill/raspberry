# Requirements Document

## Introduction

Este documento define los requisitos para configurar una infraestructura Docker en una Raspberry Pi 4 (ARM64) que permita ejecutar múltiples proyectos como contenedores aislados. La infraestructura incluye instalación y configuración de Docker y Docker Compose, gestión de contenedores, redes entre servicios, almacenamiento persistente, monitoreo básico y prácticas de seguridad para un servidor doméstico.

## Glossary

- **Sistema_Infra**: El conjunto de scripts, configuraciones y servicios que conforman la infraestructura Docker en la Raspberry Pi 4
- **Docker_Engine**: El motor de contenedores Docker instalado y configurado para la arquitectura ARM64
- **Compose_Service**: El servicio Docker Compose que orquesta múltiples contenedores definidos en archivos de configuración
- **Contenedor**: Una instancia aislada de un servicio o proyecto ejecutándose dentro de Docker
- **Red_Interna**: La red virtual Docker que permite la comunicación entre contenedores
- **Volumen_Persistente**: Un volumen Docker montado en el sistema de archivos del host para preservar datos entre reinicios
- **Monitor_Salud**: El componente que verifica el estado de salud de los contenedores y reporta anomalías
- **Administrador**: La persona que gestiona y opera la infraestructura Docker en la Raspberry Pi 4

## Requirements

### Requisito 1: Instalación de Docker Engine

**Historia de Usuario:** Como Administrador, quiero instalar Docker Engine optimizado para ARM64, para poder ejecutar contenedores en la Raspberry Pi 4.

#### Criterios de Aceptación

1. WHEN el script de instalación se ejecuta en una Raspberry Pi 4 con sistema operativo de 64 bits, THE Sistema_Infra SHALL instalar Docker Engine compatible con la arquitectura ARM64
2. WHEN la instalación de Docker Engine finaliza, THE Sistema_Infra SHALL verificar que el servicio Docker está activo y responde al comando `docker info` con código de salida 0 en un máximo de 30 segundos
3. WHEN la instalación de Docker Engine finaliza, THE Sistema_Infra SHALL configurar Docker para iniciarse automáticamente con el sistema operativo mediante systemd
4. IF la instalación de Docker Engine falla, THEN THE Sistema_Infra SHALL registrar el error en la salida estándar de errores con un mensaje descriptivo y sugerir acciones correctivas
5. IF el sistema operativo no es de 64 bits o la arquitectura no es ARM64, THEN THE Sistema_Infra SHALL mostrar un mensaje de error indicando los requisitos del sistema y terminar la ejecución con código de salida distinto de 0

### Requisito 2: Instalación de Docker Compose

**Historia de Usuario:** Como Administrador, quiero instalar Docker Compose, para poder orquestar múltiples contenedores mediante archivos de configuración declarativos.

#### Criterios de Aceptación

1. WHEN el script de instalación se ejecuta, THE Sistema_Infra SHALL instalar Docker Compose en versión 2.20.0 o superior compatible con la arquitectura ARM64
2. WHEN la instalación de Docker Compose finaliza, THE Sistema_Infra SHALL verificar que el comando `docker compose version` se ejecuta con código de salida 0 y retorna una cadena de versión válida en un tiempo máximo de 10 segundos
3. IF la versión de Docker Compose instalada es inferior a la versión mínima requerida para el formato de archivo Compose utilizado en el proyecto, THEN THE Sistema_Infra SHALL mostrar un mensaje de error en la salida estándar indicando la versión instalada y la versión mínima requerida
4. IF la instalación de Docker Compose falla por error de red, permisos insuficientes o paquete no disponible, THEN THE Sistema_Infra SHALL mostrar un mensaje de error indicando la causa del fallo y terminar la ejecución con un código de salida distinto de 0
5. IF Docker Engine no está instalado o no está en ejecución al momento de instalar Docker Compose, THEN THE Sistema_Infra SHALL mostrar un mensaje de error indicando que Docker Engine es un prerequisito y terminar la ejecución con un código de salida distinto de 0

### Requisito 3: Gestión de Contenedores

**Historia de Usuario:** Como Administrador, quiero gestionar los contenedores de forma sencilla, para poder iniciar, detener y reiniciar servicios sin complejidad.

#### Criterios de Aceptación

1. WHEN el Administrador ejecuta el comando de inicio, THE Compose_Service SHALL iniciar todos los contenedores definidos en el archivo de configuración en orden topológico según sus dependencias declaradas, esperando un máximo de 60 segundos por contenedor para alcanzar el estado operativo
2. WHEN el Administrador ejecuta el comando de detención, THE Compose_Service SHALL detener todos los contenedores en orden inverso al de dependencias, enviando señal SIGTERM y esperando un máximo de 10 segundos antes de forzar la terminación con SIGKILL
3. WHEN el Administrador ejecuta el comando de reinicio para un servicio específico, THE Compose_Service SHALL reiniciar únicamente el contenedor del servicio indicado sin afectar a los demás contenedores
4. WHEN el Administrador solicita el estado de los contenedores, THE Sistema_Infra SHALL mostrar el nombre, estado, puertos expuestos y tiempo de actividad de cada contenedor
5. IF un contenedor falla durante el inicio o no alcanza el estado operativo dentro del tiempo límite de 60 segundos, THEN THE Sistema_Infra SHALL registrar el error y mostrar los últimos 50 registros del contenedor fallido
6. IF el Administrador ejecuta el comando de reinicio con un nombre de servicio que no existe en el archivo de configuración, THEN THE Compose_Service SHALL mostrar un mensaje de error indicando que el servicio no fue encontrado y listar los nombres de servicios válidos disponibles

### Requisito 4: Redes entre Contenedores

**Historia de Usuario:** Como Administrador, quiero que los contenedores se comuniquen entre sí a través de una red interna, para poder construir arquitecturas de microservicios.

#### Criterios de Aceptación

1. THE Sistema_Infra SHALL crear una Red_Interna dedicada para la comunicación entre contenedores al inicializar el entorno de infraestructura
2. WHEN un contenedor se une a la Red_Interna, THE Sistema_Infra SHALL asignar un nombre DNS interno igual al nombre del servicio del contenedor, resoluble por los demás contenedores en un máximo de 5 segundos
3. WHILE los contenedores están conectados a la Red_Interna, THE Sistema_Infra SHALL permitir la comunicación entre contenedores usando nombres de servicio como direcciones de red
4. THE Sistema_Infra SHALL aislar la Red_Interna del tráfico externo excepto para los puertos explícitamente expuestos en la configuración, permitiendo entre 1 y 100 puertos expuestos por contenedor
5. IF un contenedor no puede resolver el nombre DNS de otro contenedor en la Red_Interna dentro de 5 segundos, THEN THE Sistema_Infra SHALL registrar un error de resolución DNS en el log del sistema con los nombres de servicio de origen y destino
6. WHEN un contenedor se desconecta de la Red_Interna, THE Sistema_Infra SHALL eliminar su entrada DNS interna en un máximo de 10 segundos para que los demás contenedores dejen de resolver su nombre de servicio

### Requisito 5: Almacenamiento Persistente

**Historia de Usuario:** Como Administrador, quiero que los datos de los contenedores persistan entre reinicios, para no perder información cuando un contenedor se detiene o actualiza.

#### Criterios de Aceptación

1. THE Sistema_Infra SHALL definir un Volumen_Persistente para cada servicio que gestione datos de estado (bases de datos, colas de mensajes y archivos de configuración generados en tiempo de ejecución)
2. WHEN un contenedor se reinicia o actualiza, THE Volumen_Persistente SHALL preservar todos los datos almacenados previamente sin pérdida ni corrupción verificable mediante comparación de integridad antes y después del reinicio
3. THE Sistema_Infra SHALL almacenar los volúmenes en una ruta del sistema de archivos del host definida mediante variable de entorno, con un valor por defecto documentado si la variable no está configurada
4. IF la ruta configurada para volúmenes no existe o no es accesible con permisos de lectura y escritura, THEN THE Sistema_Infra SHALL impedir el inicio del contenedor afectado y registrar un mensaje de error indicando la ruta inválida y el permiso faltante
5. WHEN el Administrador solicita información de volúmenes, THE Sistema_Infra SHALL mostrar el nombre, tamaño en megabytes y contenedor asociado de cada Volumen_Persistente
6. IF el espacio disponible en disco es inferior al 10% de la capacidad total, THEN THE Sistema_Infra SHALL notificar al Administrador con el espacio restante en megabytes, verificando el espacio cada 60 segundos y emitiendo como máximo una notificación cada 10 minutos mientras la condición persista

### Requisito 6: Monitoreo y Verificación de Salud

**Historia de Usuario:** Como Administrador, quiero monitorear el estado de los contenedores, para poder detectar y resolver problemas antes de que afecten a los servicios.

#### Criterios de Aceptación

1. THE Monitor_Salud SHALL verificar el estado de cada contenedor activo en intervalos de 30 segundos, comprobando que el proceso principal del contenedor se encuentra en ejecución y que responde dentro de un tiempo máximo de 5 segundos por intento
2. WHEN un contenedor no responde a la verificación de salud durante 3 intentos consecutivos, THE Monitor_Salud SHALL marcar el contenedor como no saludable y registrar la marca de tiempo del cambio de estado
3. WHEN un contenedor es marcado como no saludable, THE Monitor_Salud SHALL reiniciar automáticamente el contenedor afectado, hasta un máximo de 3 reintentos en un período de 5 minutos
4. IF un contenedor alcanza el máximo de 3 reintentos fallidos en un período de 5 minutos, THEN THE Monitor_Salud SHALL marcar el contenedor como en estado crítico, detener los intentos de reinicio y generar una alerta indicando el nombre del contenedor y el número de reintentos fallidos
5. THE Monitor_Salud SHALL registrar el uso de CPU, memoria y red de cada contenedor en cada ciclo de verificación de 30 segundos
6. WHEN el uso de memoria de un contenedor supera el 85% del límite asignado, THE Monitor_Salud SHALL generar una alerta con el nombre del contenedor y el porcentaje de uso actual
7. WHEN el uso de CPU de un contenedor supera el 90% durante 3 ciclos consecutivos de verificación, THE Monitor_Salud SHALL generar una alerta con el nombre del contenedor y el porcentaje de uso promedio
8. IF el Monitor_Salud no puede conectarse a Docker Engine, THEN THE Monitor_Salud SHALL registrar el error, suspender la verificación de contenedores y reintentar la conexión cada 60 segundos hasta un máximo de 10 intentos
9. IF el Monitor_Salud agota los 10 intentos de reconexión a Docker Engine, THEN THE Monitor_Salud SHALL generar una alerta indicando la pérdida de conexión y la duración de la desconexión

### Requisito 7: Seguridad del Servidor Doméstico

**Historia de Usuario:** Como Administrador, quiero aplicar prácticas de seguridad en la infraestructura Docker, para proteger el servidor doméstico contra accesos no autorizados y vulnerabilidades.

#### Criterios de Aceptación

1. THE Sistema_Infra SHALL ejecutar todos los contenedores con un usuario no root dentro del contenedor
2. THE Sistema_Infra SHALL limitar los recursos de CPU y memoria asignados a cada contenedor según los valores definidos en la configuración de cada servicio dentro del archivo de composición Docker
3. THE Sistema_Infra SHALL deshabilitar la escalación de privilegios en todos los contenedores mediante la directiva de seguridad correspondiente (security_opt: no-new-privileges)
4. WHEN un contenedor expone puertos al host, THE Sistema_Infra SHALL vincular los puertos únicamente a la interfaz de red local (127.0.0.1) excepto cuando se configure explícitamente lo contrario
5. THE Sistema_Infra SHALL configurar el reinicio automático de contenedores con una política de máximo 5 reintentos para prevenir bucles de reinicio
6. WHEN se procesa un archivo de composición Docker que referencia una imagen sin etiqueta de versión específica (latest o sin etiqueta), THE Sistema_Infra SHALL generar una advertencia en los logs recomendando fijar una versión concreta
7. THE Sistema_Infra SHALL almacenar secretos y credenciales en archivos de entorno separados (.env) excluidos del control de versiones mediante reglas en el archivo .gitignore
8. IF un servicio requiere ejecución como usuario root para funcionar correctamente, THEN THE Sistema_Infra SHALL documentar la excepción en la configuración del servicio con una justificación y limitar los permisos adicionales al mínimo necesario
9. IF un contenedor no tiene definidos límites de CPU o memoria en su configuración, THEN THE Sistema_Infra SHALL aplicar los límites por defecto de 1 núcleo de CPU y 512 MB de memoria RAM

### Requisito 8: Configuración Base Multi-Proyecto

**Historia de Usuario:** Como Administrador, quiero una estructura base que soporte múltiples proyectos, para poder agregar y eliminar servicios de forma modular.

#### Criterios de Aceptación

1. THE Sistema_Infra SHALL organizar la configuración en una estructura de directorios con un archivo principal de composición y archivos de configuración independientes por servicio
2. WHEN el Administrador agrega un nuevo servicio, THE Compose_Service SHALL integrar el servicio de modo que el nuevo servicio se inicie correctamente y los servicios existentes continúen ejecutándose sin reinicio ni cambios en sus archivos de configuración
3. WHEN el Administrador elimina un servicio, THE Compose_Service SHALL remover el servicio deteniendo únicamente sus contenedores, preservando los volúmenes de datos asociados al servicio eliminado y manteniendo en ejecución los demás servicios sin reinicio
4. THE Sistema_Infra SHALL proporcionar un archivo de configuración de ejemplo que contenga comentarios descriptivos para cada parámetro configurable y las instrucciones mínimas para agregar un nuevo servicio
5. WHEN el Administrador solicita aplicar cambios en la configuración, THE Sistema_Infra SHALL validar la sintaxis de todos los archivos de configuración involucrados antes de ejecutar los cambios
6. IF la validación de sintaxis detecta errores en los archivos de configuración, THEN THE Sistema_Infra SHALL rechazar la aplicación de cambios, mostrar un mensaje indicando el archivo y la línea con el error, y preservar la configuración activa sin modificaciones
