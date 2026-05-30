# Pi-hole — Bloqueador de anuncios a nivel de red

Pi-hole es un servidor DNS que bloquea dominios de anuncios, trackers y malware antes de que lleguen a tus dispositivos. Funciona para toda tu red local sin necesidad de instalar nada en cada dispositivo.

## Qué bloquea

- Anuncios en webs y apps
- Trackers de seguimiento
- Dominios de malware y phishing
- Telemetría no deseada (smart TVs, IoT, etc.)

## Requisitos

- La infraestructura Docker ya instalada (`./install.sh` ejecutado)
- Puerto 53 libre en la Raspberry Pi (no tener otro DNS corriendo)
- Puerto 8080 libre para el panel web

## Instalación

### 1. Configurar la contraseña

Editar `.env` en la raíz del proyecto:

```bash
nano .env
```

Cambiar estas variables:

```env
# Contraseña para el panel de administración de Pi-hole
PIHOLE_WEBPASSWORD=tu-contraseña-segura

# Tu zona horaria
PIHOLE_TZ=Europe/Madrid
```

### 2. Iniciar el servicio

```bash
./manage.sh start
```

### 3. Verificar que funciona

```bash
./manage.sh status
```

Deberías ver `pihole` con estado `running`.

Prueba que resuelve DNS:

```bash
dig @127.0.0.1 google.com
```

## Acceder al panel de administración

Abre en tu navegador:

```
http://<ip-de-tu-raspberry>:8080/admin
```

Usa la contraseña que configuraste en `PIHOLE_WEBPASSWORD`.

Desde el panel puedes:
- Ver estadísticas de consultas bloqueadas
- Añadir dominios a la lista blanca o negra
- Cambiar los servidores DNS upstream
- Ver qué dispositivos hacen más consultas
- Configurar listas de bloqueo adicionales

## Configurar tu red para usar Pi-hole

### Opción A: Configurar en el router (recomendado)

Esto hace que TODOS los dispositivos de tu red usen Pi-hole automáticamente.

1. Accede a la configuración de tu router (normalmente `192.168.1.1`)
2. Busca la sección de DHCP o DNS
3. Cambia el DNS primario a la IP de tu Raspberry Pi
4. Deja el DNS secundario vacío (o pon la IP de la Raspberry también)
5. Guarda y reinicia el router

> **Nota**: Si pones un DNS secundario diferente (como 8.8.8.8), algunos dispositivos lo usarán directamente y no se bloquearán los anuncios para ellos.

### Opción B: Configurar por dispositivo

Si no quieres tocar el router, configura el DNS manualmente en cada dispositivo:

**macOS:**
- Preferencias del Sistema → Red → Wi-Fi → Detalles → DNS
- Añadir la IP de tu Raspberry Pi

**iOS:**
- Ajustes → Wi-Fi → (i) junto a tu red → Configurar DNS → Manual
- Añadir la IP de tu Raspberry Pi

**Android:**
- Ajustes → Wi-Fi → Mantener pulsada tu red → Modificar red → Opciones avanzadas
- IP estática → DNS 1: IP de tu Raspberry Pi

**Windows:**
- Panel de control → Red → Adaptador → Propiedades → IPv4 → Propiedades
- Usar las siguientes direcciones de servidor DNS: IP de tu Raspberry Pi

**Linux:**
```bash
# Temporal
echo "nameserver <ip-raspberry>" | sudo tee /etc/resolv.conf

# Permanente (systemd-resolved)
sudo nano /etc/systemd/resolved.conf
# Añadir: DNS=<ip-raspberry>
sudo systemctl restart systemd-resolved
```

## Configuración avanzada

### Cambiar servidores DNS upstream

Por defecto usa Cloudflare (1.1.1.1) y Google (8.8.8.8). Para cambiarlo:

1. Panel web → Settings → DNS
2. Elegir otros proveedores o poner DNS personalizados

Opciones populares:
| Proveedor | DNS primario | DNS secundario |
|-----------|-------------|----------------|
| Cloudflare | 1.1.1.1 | 1.0.0.1 |
| Google | 8.8.8.8 | 8.8.4.4 |
| Quad9 | 9.9.9.9 | 149.112.112.112 |
| OpenDNS | 208.67.222.222 | 208.67.220.220 |

### Añadir listas de bloqueo adicionales

1. Panel web → Adlists
2. Añadir URLs de listas. Algunas recomendadas:

```
https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts
https://raw.githubusercontent.com/PolishFiltersTeam/KADhosts/master/KADhosts.txt
https://raw.githubusercontent.com/FadeMind/hosts.extras/master/add.Spam/hosts
```

3. Ir a Tools → Update Gravity para aplicar las nuevas listas

### Añadir dominios a la lista blanca

Si Pi-hole bloquea algo que necesitas:

1. Panel web → Whitelist
2. Añadir el dominio (ej: `login.microsoftonline.com`)

O desde la terminal:

```bash
docker exec pihole pihole -w dominio.com
```

### Añadir dominios a la lista negra

Para bloquear un dominio específico:

```bash
docker exec pihole pihole -b dominio-molesto.com
```

## Mantenimiento

### Ver logs

```bash
./manage.sh logs pihole
```

### Actualizar las listas de bloqueo

```bash
docker exec pihole pihole -g
```

O desde el panel: Tools → Update Gravity

### Actualizar Pi-hole

Editar `services/pihole/docker-compose.override.yml` y cambiar la versión de la imagen:

```yaml
image: pihole/pihole:2024.07.0  # Cambiar a la nueva versión
```

Luego:

```bash
./manage.sh stop
docker pull pihole/pihole:<nueva-version>
./manage.sh start
```

### Reiniciar Pi-hole

```bash
./manage.sh restart pihole
```

## Solución de problemas

### No se bloquean anuncios

1. Verificar que el dispositivo usa la IP de la Raspberry como DNS:
   ```bash
   nslookup google.com <ip-raspberry>
   ```
2. Verificar que Pi-hole está corriendo: `./manage.sh status`
3. Comprobar que el puerto 53 responde: `dig @<ip-raspberry> google.com`

### El panel web no carga

1. Verificar que el contenedor está activo: `./manage.sh status`
2. Verificar el puerto: `curl http://<ip-raspberry>:8080`
3. Ver logs: `./manage.sh logs pihole`

### Alguna web no funciona

Probablemente Pi-hole está bloqueando un dominio necesario:

1. Panel web → Query Log → buscar el dominio
2. Si aparece bloqueado, añadirlo a la lista blanca

### Pi-hole consume mucha memoria

El límite está en 256MB. Si necesitas más:

Editar `services/pihole/docker-compose.override.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 512M  # Aumentar según necesidad
```

### Conflicto con puerto 53

Si otro servicio usa el puerto 53 (como `systemd-resolved` en Ubuntu):

```bash
# En la Raspberry Pi
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
```

## Datos persistentes

Los datos de Pi-hole se almacenan en:
- `volumes/pihole/etc-pihole/` — Configuración, listas, base de datos de consultas
- `volumes/pihole/etc-dnsmasq.d/` — Configuración DNS personalizada

Estos datos persisten entre reinicios y actualizaciones del contenedor.

## Recursos

- [Documentación oficial de Pi-hole](https://docs.pi-hole.net/)
- [Pi-hole Docker en GitHub](https://github.com/pi-hole/docker-pi-hole)
- [Listas de bloqueo comunitarias](https://firebog.net/)
