# Campus Locator

Aplicación Android (Kotlin) que ayuda a personas con discapacidad visual a identificar
su ubicación dentro de un campus a partir de fotos tomadas con la cámara del teléfono,
comparándolas contra un banco de imágenes de referencia recolectado previamente.

La app tiene **dos flujos dentro de un mismo proyecto y un mismo APK**:

1. **Flujo público (usuario final):** cualquier persona puede abrir la app, tomar 3
   fotos de su entorno girando el teléfono, y recibir como resultado su ubicación
   aproximada dentro del campus (ej. "Estás cerca de la biblioteca y del bloque de
   los trillizos"), con soporte de lector de pantalla.
2. **Flujo protegido (recolector / admin):** tras iniciar sesión con una cuenta con
   rol de administrador, se habilita el panel "Recolector de Imágenes", donde el
   equipo encargado puede crear puntos del campus, subir fotos de referencia por
   punto, y ver estadísticas de uso (puntos más buscados, tendencias, etc.).

No son dos apps independientes: es **una sola app** cuya interfaz de administración
se activa según el rol del usuario autenticado.

## ¿Cómo funciona el flujo público?

| Paso | Pantalla | Descripción |
|---|---|---|
| 1 | Inicio | El usuario presiona un botón para comenzar la identificación. |
| 2 | Captura (1/2/3) | Se piden 3 fotos, girando al menos 30° entre cada una, validando el ángulo con el sensor de orientación. |
| 3 | Resultado | Se muestra la ubicación estimada, un mapa con puntos de referencia cercanos, y la opción de activar lectura por voz de las instrucciones. |

## ¿Cómo funciona el flujo de recolector (admin)?

| Sección | Descripción |
|---|---|
| Puntos | CRUD de "puntos del campus" (nombre, descripción, categoría, imágenes asociadas). |
| Imágenes | Galería global de todas las imágenes recolectadas, con filtros por punto/fecha, subida de nuevas imágenes y detalle de cada imagen (metadata, notas, estado de sincronización). |
| Estadísticas | Dashboard con puntos más accedidos, correlación con búsquedas, tendencia de visualizaciones y distribución por categoría. |

Las imágenes subidas en el flujo de recolector son las que alimentan el modelo/base de
comparación que usa el flujo público para identificar ubicaciones.

## Requisitos

- Android Studio (última versión estable)
- Kotlin
- SDK mínimo / objetivo: *(definir según dispositivos objetivo)*
- Jetpack Compose
- Acceso a cámara y sensores de orientación del dispositivo

## Cómo correr el proyecto

1. Clona el repositorio y ábrelo en Android Studio.
2. Sincroniza Gradle (`File > Sync Project with Gradle Files`).
3. Ejecuta la configuración `app` sobre un emulador o dispositivo físico
   (se recomienda dispositivo físico para probar cámara y sensores).

## Estructura del proyecto

Ver [`ARCHITECTURE.md`](./ARCHITECTURE.md) para el detalle completo de organización de
paquetes, capas (UI / domain / data), navegación y manejo de sesión/roles.

## Estado del proyecto

En desarrollo. Este documento y `ARCHITECTURE.md` se actualizan a medida que el
proyecto avanza; si cambia una decisión de arquitectura, refléjalo también aquí.