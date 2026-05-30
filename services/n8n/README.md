# n8n — Automatización de flujos de trabajo

Plataforma visual para crear automatizaciones conectando servicios entre sí. Como Zapier o IFTTT pero self-hosted y sin límites.

## Acceso

```
http://<ip-raspberry>:5678
```

La primera vez te pedirá crear una cuenta de administrador.

## Qué puedes automatizar

### Ejemplos prácticos con tu setup

**Monitoreo → Notificaciones:**
- Si un contenedor cae → enviar notificación por Ntfy
- Si el disco está al 90% → alerta al móvil
- Cada mañana → resumen de lo que bloqueó Pi-hole

**Archivos y documentos:**
- Cuando llega un email con adjunto PDF → guardarlo en una carpeta
- Cuando se añade un libro a Calibre → notificación

**Programación:**
- Cada lunes a las 9:00 → enviar resumen semanal
- Cada hora → verificar si hay actualizaciones de contenedores

**Integraciones externas:**
- Mensaje en Telegram → ejecutar comando en la Raspberry
- Nuevo post en un feed RSS → notificación por Ntfy
- Webhook de GitHub → desplegar actualización

## Crear tu primer flujo

1. Acceder a `http://<ip-raspberry>:5678`
2. Click en "New Workflow"
3. Añadir un trigger (ej: "Schedule Trigger" → cada hora)
4. Añadir una acción (ej: "HTTP Request" → llamar a Ntfy)
5. Conectar los nodos
6. Activar el workflow

### Ejemplo: Alerta de disco lleno

```
[Schedule Trigger: cada 5 min]
    → [Execute Command: df -h / | awk '{print $5}']
    → [IF: uso > 90%]
        → [HTTP Request: POST http://ntfy:80/disco con mensaje]
```

## Nodos útiles para tu Raspberry

| Nodo | Uso |
|------|-----|
| Schedule Trigger | Ejecutar cada X minutos/horas |
| Webhook | Recibir llamadas HTTP externas |
| Execute Command | Ejecutar comandos en el sistema |
| HTTP Request | Llamar APIs (Ntfy, Pi-hole, etc.) |
| IF | Condiciones (si X entonces Y) |
| Email | Enviar/recibir emails |
| Telegram | Bot de Telegram |
| RSS Feed | Leer feeds RSS |

## Conectar con otros servicios de tu Raspberry

n8n puede comunicarse con los demás contenedores usando los nombres DNS internos:

```
Pi-hole API:    http://pihole:80/admin/api.php
Ntfy:           http://ntfy:80/<topic>
Calibre-web:    http://calibre-web:8083
Portainer API:  https://portainer:9443/api
```

## Uso de recursos

- RAM: ~200-300MB (puede subir con muchos workflows activos)
- CPU: Bajo en reposo, picos al ejecutar workflows
- Disco: ~100MB + datos de workflows

## Backups

Los datos de n8n (workflows, credenciales, historial) están en:
```
volumes/n8n/
```

Para exportar workflows manualmente:
- Settings → Export → Download all workflows

## Actualizar

```bash
# Editar versión en docker-compose.override.yml
./manage.sh stop
docker pull n8nio/n8n:<nueva-version>
./manage.sh start
```

## Solución de problemas

### Workflows no se ejecutan
- Verificar que el workflow está "Active" (toggle verde)
- Ver el historial de ejecuciones en "Executions"

### No puede conectar con otros servicios
- Usar nombres DNS internos (no localhost ni IP)
- Verificar que el servicio destino está corriendo: `./manage.sh status`

### Se queda sin memoria
- Reducir el historial de ejecuciones: Settings → Pruning
- Desactivar workflows que no uses
- Aumentar el límite de memoria en docker-compose.override.yml si es necesario
