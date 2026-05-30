# Portainer — Panel web para gestionar Docker

Interfaz visual para gestionar todos tus contenedores, imágenes, redes y volúmenes desde el navegador.

## Acceso

```
https://<ip-raspberry>:9443
```

La primera vez te pedirá crear un usuario administrador.

## Qué puedes hacer

- Ver el estado de todos los contenedores en tiempo real
- Iniciar, detener, reiniciar contenedores con un click
- Ver logs de cualquier contenedor
- Inspeccionar redes y volúmenes
- Actualizar imágenes Docker
- Acceder a la terminal de un contenedor desde el navegador
- Ver uso de recursos (CPU, RAM) por contenedor

## Instalación

Ya está configurado. Solo necesitas:

```bash
./manage.sh start
```

Accede a `https://<ip-raspberry>:9443` y crea tu usuario admin.

> Nota: El navegador mostrará una advertencia de certificado SSL (es auto-firmado). Acepta la excepción.

## Uso de recursos

- RAM: ~30MB
- CPU: Mínimo
- Disco: ~50MB

## Notas de seguridad

- Portainer tiene acceso de solo lectura al socket de Docker
- El panel está protegido por usuario/contraseña
- Usa HTTPS por defecto (puerto 9443)
- Si expones a internet, añade autenticación adicional (Authelia)

## Actualizar

```bash
# Editar la versión en docker-compose.override.yml
# image: portainer/portainer-ce:X.XX.X-alpine
./manage.sh stop
docker pull portainer/portainer-ce:<nueva-version>-alpine
./manage.sh start
```
