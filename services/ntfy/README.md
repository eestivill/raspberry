# Ntfy — Notificaciones push a tu móvil

Servidor de notificaciones que te permite enviar alertas desde cualquier script o servicio directamente a tu teléfono.

## Acceso

```
http://<ip-raspberry>:8090
```

## Enviar una notificación

Desde cualquier terminal o script:

```bash
curl -d "Backup completado con éxito" http://<ip-raspberry>:8090/alertas
```

Con título y prioridad:

```bash
curl \
  -H "Title: Disco lleno" \
  -H "Priority: high" \
  -H "Tags: warning" \
  -d "Queda menos del 10% de espacio en disco" \
  http://<ip-raspberry>:8090/alertas
```

## Recibir notificaciones en el móvil

### Android
1. Instalar la app [Ntfy](https://play.google.com/store/apps/details?id=io.heckel.ntfy) desde Play Store
2. Añadir suscripción → Servidor: `http://<ip-raspberry>:8090`
3. Topic: `alertas` (o el que uses)

### iOS
1. Instalar la app [Ntfy](https://apps.apple.com/app/ntfy/id1625396347) desde App Store
2. Misma configuración que Android

## Integración con el monitor de salud

Puedes modificar el `health_monitor.py` para enviar alertas por Ntfy cuando un contenedor cae:

```python
import requests

def send_ntfy_alert(message, title="Alerta RPi4", priority="high"):
    requests.post(
        "http://ntfy:80/alertas",  # Usa el nombre DNS interno
        data=message,
        headers={"Title": title, "Priority": priority}
    )
```

## Ejemplos de uso

### Alerta cuando termina un proceso largo
```bash
long_running_command && curl -d "Proceso completado" http://raspberry:8090/tareas
```

### Alerta desde un cron job
```bash
# En crontab
0 3 * * * /home/pi/backup.sh && curl -d "Backup nocturno OK" http://localhost:8090/backups
```

### Alerta con emoji y acción
```bash
curl \
  -H "Title: Nueva actualización" \
  -H "Tags: rocket" \
  -H "Actions: view, Abrir panel, https://<ip-raspberry>:9443" \
  -d "Hay actualizaciones disponibles para 3 contenedores" \
  http://localhost:8090/updates
```

## Topics sugeridos

| Topic | Uso |
|-------|-----|
| `alertas` | Alertas generales del sistema |
| `backups` | Estado de backups |
| `docker` | Eventos de contenedores |
| `disco` | Alertas de espacio en disco |
| `seguridad` | Alertas de seguridad |

## Uso de recursos

- RAM: ~15MB
- CPU: Mínimo
- Disco: Depende del cache de mensajes

## Actualizar

```bash
# Editar versión en docker-compose.override.yml
./manage.sh stop
docker pull binwiederhier/ntfy:<nueva-version>
./manage.sh start
```
