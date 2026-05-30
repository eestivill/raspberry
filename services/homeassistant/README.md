# Home Assistant — Panel de control de consolas

Panel web sencillo para que tus visitas puedan encender y apagar las consolas retro conectadas a enchufes Osram Smart+ controlados vía Alexa.

## Acceso

```
http://<ip-raspberry>:8123
```

## Configuración inicial

### 1. Iniciar Home Assistant

```bash
./manage.sh start
```

La primera vez tarda 2-3 minutos en arrancar. Accede a `http://<ip-raspberry>:8123`.

### 2. Crear cuenta de administrador

Sigue el asistente de configuración:
- Nombre, usuario y contraseña
- Ubicación (para zona horaria)
- Detectará dispositivos en tu red automáticamente

### 3. Integrar con Alexa

Para controlar los enchufes Osram a través de Alexa:

1. Ir a **Settings → Devices & Services → Add Integration**
2. Buscar **"Alexa Media Player"** (integración HACS) o **"Amazon Alexa"**
3. Iniciar sesión con tu cuenta de Amazon
4. Home Assistant descubrirá los enchufes que ya tienes en Alexa

> **Nota**: La integración oficial de Alexa requiere una suscripción a Nabu Casa (~5€/mes). La alternativa gratuita es instalar HACS + Alexa Media Player (ver sección HACS abajo).

### 4. Instalar HACS (gratuito)

HACS es una tienda de integraciones comunitarias para Home Assistant:

```bash
# Dentro del contenedor
docker exec -it homeassistant bash
wget -O - https://get.hacs.xyz | bash -
```

Reiniciar Home Assistant, luego:
1. Settings → Devices & Services → Add Integration → HACS
2. Seguir instrucciones (vincular con GitHub)
3. Una vez instalado HACS: HACS → Integrations → buscar "Alexa Media Player"
4. Instalar y configurar con tu cuenta de Amazon

### 5. Verificar que los enchufes aparecen

Ir a **Settings → Devices & Services → Entities**. Deberías ver tus 4 enchufes Osram como `switch.play`, `switch.wii`, etc. (los nombres dependen de cómo los tengas en Alexa).

## Crear el panel de consolas

### Panel automático (dashboard)

1. Ir a **Overview** (panel principal)
2. Click en los 3 puntos → **Edit Dashboard**
3. Click en **+ Add Card**
4. Seleccionar **"Button"**
5. Configurar:
   - Entity: `switch.play` (o como se llame tu enchufe)
   - Name: "PlayStation"
   - Icon: `mdi:sony-playstation`
   - Tap action: Toggle
6. Repetir para cada consola

## Panel con YAML (más control)

Crear un dashboard personalizado. Ir a Settings → Dashboards → Add Dashboard → "Consolas".

Luego editar en modo YAML y pegar:

```yaml
title: Consolas
views:
  - title: Consolas
    icon: mdi:gamepad-variant
    cards:
      - type: markdown
        content: |
          ## 📺 Switch HDMI
          | Entrada | Consola |
          |---------|---------|
          | HDMI 1 | PlayStation |
          | HDMI 2 | Wii |
          | HDMI 3 | Retron 5 |
          | HDMI 4 | Switch |
          | HDMI 5 | Gamecube |

      - type: grid
        columns: 2
        square: true
        cards:
          - type: button
            entity: switch.play
            name: "1. PlayStation"
            icon: mdi:sony-playstation
            tap_action:
              action: toggle
            icon_height: 80px
            show_state: true

          - type: button
            entity: switch.wii
            name: "2. Wii"
            icon: mdi:nintendo-wii
            tap_action:
              action: toggle
            icon_height: 80px
            show_state: true

          - type: button
            entity: switch.retron_5
            name: "3. Retron 5"
            icon: mdi:gamepad-classic
            tap_action:
              action: toggle
            icon_height: 80px
            show_state: true

          - type: button
            entity: switch.switch
            name: "4. Switch"
            icon: mdi:nintendo-switch
            tap_action:
              action: toggle
            icon_height: 80px
            show_state: true
```

> **Importante**: Cambia los `entity` por los nombres reales que aparezcan en tu Home Assistant (dependen de cómo los tengas nombrados en Alexa).

## Acceso para visitas (sin cuenta)

Para que las visitas puedan usar el panel sin crear cuenta:

### Opción A: Usuario invitado

1. Settings → People → Add Person
2. Crear usuario "Invitado" con contraseña simple (ej: "1234")
3. Asignar solo el dashboard de "Consolas"
4. Compartir la URL: `http://<ip-raspberry>:8123/consolas`

### Opción B: Panel Kiosk (sin login)

Instalar desde HACS la integración "Kiosk Mode":
1. HACS → Frontend → buscar "Kiosk Mode"
2. Instalar
3. Configurar para ocultar menús y sidebar en el dashboard de consolas

### Opción C: Código QR

Generar un QR con la URL del panel para que las visitas lo escaneen con el móvil:
```
http://<ip-raspberry>:8123/consolas
```

Puedes imprimir el QR y ponerlo junto a las consolas.

## Iconos disponibles para consolas

| Consola | Icono |
|---------|-------|
| PlayStation | `mdi:sony-playstation` |
| Wii | `mdi:nintendo-wii` |
| Switch | `mdi:nintendo-switch` |
| Gamecube | `mdi:nintendo-gamecube` |
| Retron 5 | `mdi:gamepad-classic` |
| Xbox | `mdi:microsoft-xbox` |
| Genérico | `mdi:gamepad-variant` |
| TV | `mdi:television` |
| Enchufe | `mdi:power-plug` |

## Automatizaciones útiles

### Apagar todo a las 2:00 AM (por si se olvidan)

Settings → Automations → Create Automation:
- Trigger: Time = 02:00
- Action: Turn off → seleccionar los 4 enchufes

### Notificación cuando se enciende una consola

- Trigger: State change → switch.play → on
- Action: Notify → Ntfy → "Alguien ha encendido la PlayStation"

```yaml
# En automations.yaml
- alias: "Notificar consola encendida"
  trigger:
    - platform: state
      entity_id:
        - switch.play
        - switch.wii
        - switch.switch
        - switch.retron_5
      to: "on"
  action:
    - service: rest_command.ntfy_alert
      data:
        message: "{{ trigger.to_state.name }} encendida"
```

## Uso de recursos

- RAM: ~300-400MB
- CPU: Bajo en reposo, picos al cargar dashboards
- Disco: ~500MB (incluye base de datos de historial)

## Solución de problemas

### Los enchufes no aparecen
- Verificar que están configurados en la app de Alexa
- Verificar que la integración Alexa Media Player está conectada
- Ir a Settings → Devices & Services → Alexa → "Reload"

### El panel tarda en cargar
- Home Assistant tarda 1-2 min en arrancar completamente
- Verificar con `./manage.sh status` que está "healthy"

### Alexa no responde
- La integración requiere internet
- Verificar conexión: `ping amazon.com` desde la Raspberry
- Re-autenticar en Settings → Integrations → Alexa

### Quiero control sin internet
- Comprar un dongle Zigbee (ConBee II o Sonoff Zigbee 3.0, ~15€)
- Instalar la integración ZHA o Zigbee2MQTT
- Los enchufes Osram Smart+ se emparejan directamente sin Alexa

## Actualizar

```bash
# Editar versión en docker-compose.override.yml
./manage.sh stop
docker pull ghcr.io/home-assistant/home-assistant:<nueva-version>
./manage.sh start
```

## Recursos

- [Documentación oficial](https://www.home-assistant.io/docs/)
- [HACS](https://hacs.xyz/)
- [Alexa Media Player](https://github.com/alandtse/alexa_media_player)
- [Iconos MDI](https://pictogrammers.com/library/mdi/)
