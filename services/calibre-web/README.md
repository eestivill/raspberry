# Calibre-web — Biblioteca de ebooks

Tu biblioteca personal de ebooks accesible desde cualquier dispositivo con navegador.

## Acceso

```
http://<ip-raspberry>:8083
```

Credenciales por defecto: `admin` / `admin123` (cambiar inmediatamente).

## Primera configuración

1. Acceder a `http://<ip-raspberry>:8083`
2. Login con `admin` / `admin123`
3. Te pedirá la ruta de la base de datos Calibre: `/books`
4. Cambiar la contraseña en Admin → Edit Users → admin

## Subir libros

### Desde la interfaz web
1. Click en "Upload" (arriba a la derecha)
2. Seleccionar archivo (epub, mobi, pdf, etc.)
3. Rellenar metadatos si quieres

### Desde la terminal (copiar archivos)
```bash
# Copiar un libro al volumen
cp mi-libro.epub volumes/calibre-web/books/
# Calibre-web lo detectará automáticamente si está en la DB
```

### Desde Calibre desktop
Si ya usas Calibre en tu ordenador:
1. Copia tu carpeta de biblioteca a `volumes/calibre-web/books/`
2. Asegúrate de que `metadata.db` está incluido

## Enviar libros al Kindle

1. Admin → Edit Users → tu usuario
2. Configurar "Kindle E-Mail" con tu dirección @kindle.com
3. Admin → Basic Configuration → Email
4. Configurar SMTP (Gmail, etc.)
5. En cualquier libro → "Send to Kindle"

## Formatos soportados

- EPUB (recomendado)
- MOBI / AZW3 (Kindle)
- PDF
- CBR / CBZ (cómics)
- FB2, LIT, DJVU, y más

## Conversión de formatos

Calibre-web puede convertir entre formatos si instalas `calibre-ebook` en el contenedor. Para la mayoría de usos, subir en EPUB es suficiente.

## Acceso desde e-reader

### Kindle
- Usa la función "Send to Kindle" por email
- O descarga el archivo .mobi desde la web

### Kobo / otros
- Accede desde el navegador del e-reader
- O descarga el epub y transfiérelo por USB/cable

## Uso de recursos

- RAM: ~80MB
- CPU: Bajo (picos al convertir formatos)
- Disco: Depende de tu biblioteca

## Estructura de datos

```
volumes/calibre-web/
├── config/          # Configuración de la app
└── books/           # Tu biblioteca de ebooks
    ├── metadata.db  # Base de datos Calibre
    ├── Author Name/
    │   └── Book Title/
    │       ├── cover.jpg
    │       └── Book Title.epub
    └── ...
```

## Actualizar

```bash
# Editar versión en docker-compose.override.yml
./manage.sh stop
docker pull lscr.io/linuxserver/calibre-web:<nueva-version>
./manage.sh start
```

## Solución de problemas

### "Database not found"
Asegúrate de que existe `volumes/calibre-web/books/metadata.db`. Si no tienes una biblioteca Calibre previa, crea una vacía:
```bash
mkdir -p volumes/calibre-web/books
# La primera vez, Calibre-web puede crear una DB vacía
```

### No puedo subir libros
Verificar permisos: `chmod -R 777 volumes/calibre-web/`
