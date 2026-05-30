# EmulatorJS — Juegos retro en el navegador

Emulador retro self-hosted que te permite jugar clásicos de NES, SNES, Game Boy, PlayStation, N64 y más directamente desde el navegador de cualquier dispositivo.

## Acceso

| URL | Uso |
|-----|-----|
| `http://<ip-raspberry>:3000` | Panel de gestión (subir ROMs, configurar) |
| `http://<ip-raspberry>:8086` | Frontend para jugar |

## Consolas soportadas

| Consola | Carpeta de ROMs | Extensiones |
|---------|----------------|-------------|
| NES | `nes/` | .nes, .zip |
| SNES | `snes/` | .smc, .sfc, .zip |
| Game Boy | `gb/` | .gb, .zip |
| Game Boy Color | `gbc/` | .gbc, .zip |
| Game Boy Advance | `gba/` | .gba, .zip |
| Nintendo 64 | `n64/` | .n64, .z64, .zip |
| Nintendo DS | `nds/` | .nds, .zip |
| Sega Genesis | `segaMD/` | .md, .bin, .zip |
| Sega Master System | `segaMS/` | .sms, .zip |
| Game Gear | `segaGG/` | .gg, .zip |
| PlayStation 1 | `psx/` | .bin+.cue, .pbp, .chd |
| PSP | `psp/` | .iso, .cso |
| Atari 2600 | `atari2600/` | .a26, .zip |
| Atari 7800 | `atari7800/` | .a78, .zip |
| Arcade (MAME) | `arcade/` | .zip |
| Neo Geo | `arcade/` | .zip |

## Primera configuración

### 1. Iniciar el servicio

```bash
./manage.sh start
```

### 2. Acceder al panel de gestión

Abrir `http://<ip-raspberry>:3000` en el navegador.

La primera vez descargará los cores de emulación (puede tardar unos minutos).

### 3. Subir ROMs

**Opción A: Desde el panel web (puerto 3000)**
1. Seleccionar la consola
2. Click en "Upload ROM"
3. Seleccionar el archivo

**Opción B: Copiar archivos directamente**
```bash
# Crear carpetas por consola
mkdir -p volumes/emulatorjs/data/roms/nes
mkdir -p volumes/emulatorjs/data/roms/snes
mkdir -p volumes/emulatorjs/data/roms/gba

# Copiar ROMs
cp mis-roms-nes/*.nes volumes/emulatorjs/data/roms/nes/
cp mis-roms-snes/*.sfc volumes/emulatorjs/data/roms/snes/
```

### 4. Escanear ROMs

En el panel de gestión (puerto 3000):
1. Ir a la consola donde subiste ROMs
2. Click en "Scan" para detectar los juegos
3. El sistema descargará carátulas automáticamente

### 5. Jugar

Abrir `http://<ip-raspberry>:8086` desde cualquier dispositivo y seleccionar un juego.

## Controles

### Teclado (por defecto)

| Acción | Tecla |
|--------|-------|
| D-pad | Flechas |
| A / B | Z / X |
| Start | Enter |
| Select | Shift |
| L / R | Q / W |

### Mando (gamepad)

Conecta un mando USB o Bluetooth al dispositivo desde el que juegas. EmulatorJS lo detecta automáticamente en navegadores compatibles (Chrome, Edge, Firefox).

### Pantalla táctil

En móviles y tablets aparecen controles virtuales en pantalla automáticamente.

## Guardar partidas

- **Save states**: Menú del emulador (ESC o icono de menú) → Save State
- Los guardados se almacenan en el navegador (localStorage)
- Si cambias de navegador/dispositivo, pierdes los guardados

## Organización recomendada de ROMs

```
volumes/emulatorjs/data/roms/
├── nes/
│   ├── Super Mario Bros.nes
│   ├── Zelda.nes
│   └── Metroid.nes
├── snes/
│   ├── Super Mario World.sfc
│   ├── Zelda - A Link to the Past.sfc
│   └── Chrono Trigger.sfc
├── gba/
│   ├── Pokemon Emerald.gba
│   └── Metroid Fusion.gba
├── n64/
│   ├── Super Mario 64.z64
│   └── Zelda - Ocarina of Time.z64
└── psx/
    └── Final Fantasy VII/
        ├── Final Fantasy VII (Disc 1).chd
        ├── Final Fantasy VII (Disc 2).chd
        └── Final Fantasy VII (Disc 3).chd
```

## Rendimiento por consola en RPi4

| Consola | Rendimiento | Notas |
|---------|-------------|-------|
| NES, SNES, GB, GBA | Excelente | Sin problemas |
| Genesis, Master System | Excelente | Sin problemas |
| N64 | Bueno | Algunos juegos pueden ir lentos |
| PS1 | Bueno | La mayoría van bien |
| PSP | Regular | Juegos 2D van bien, 3D puede ir lento |
| NDS | Bueno | Funciona bien en general |
| Arcade/MAME | Variable | Depende del juego |

## Uso de recursos

- RAM: ~100-200MB (más al emular N64/PS1)
- CPU: Variable según la consola emulada
- Disco: Depende de tu colección de ROMs

## Acceso desde fuera de casa

Si tienes WireGuard configurado, puedes jugar desde cualquier lugar conectándote a tu VPN y accediendo a `http://<ip-raspberry>:8086`.

## Solución de problemas

### No aparecen los juegos
1. Verificar que las ROMs están en la carpeta correcta de la consola
2. Ir al panel de gestión (puerto 3000) y hacer "Scan"
3. Verificar extensiones de archivo compatibles

### Un juego no carga
- Verificar que la ROM no está corrupta
- Algunos juegos necesitan BIOS específicas (PS1, GBA)
- Para PS1: usar formato .chd o .pbp (más eficiente que .bin+.cue)

### BIOS necesarias

Algunas consolas requieren archivos BIOS para funcionar:

| Consola | Archivo BIOS | Ubicación |
|---------|-------------|-----------|
| PS1 | `scph1001.bin` | `volumes/emulatorjs/data/bios/` |
| GBA | `gba_bios.bin` | `volumes/emulatorjs/data/bios/` |
| NDS | `bios7.bin`, `bios9.bin`, `firmware.bin` | `volumes/emulatorjs/data/bios/` |

### El emulador va lento
- Cerrar otras pestañas del navegador
- Usar Chrome (mejor rendimiento WebGL)
- Para N64/PS1: reducir resolución en opciones del emulador

## Actualizar

```bash
# Editar versión en docker-compose.override.yml
./manage.sh stop
docker pull lscr.io/linuxserver/emulatorjs:<nueva-version>
./manage.sh start
```

## Nota legal

EmulatorJS es software legal. Las ROMs de juegos están protegidas por copyright. Solo debes usar ROMs de juegos que poseas físicamente.
