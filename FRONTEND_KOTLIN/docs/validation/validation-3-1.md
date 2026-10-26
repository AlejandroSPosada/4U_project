# Validación 3-1 — FE-3.1 Lugares públicos y entrada al mapa

| Campo | Valor |
|---|---|
| Lote | `FE-3.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate31.py` |
| Entornos | `dev` con dispositivo físico |
| Criterios | Automáticos: C1 · Manuales: C2 |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11.

Desde el 2026-10-25 este lote no lleva alertas (decisión del usuario: «No necesitamos las alertas por el momento»): sus
comprobaciones de caché, sincronización y anuncio pasaron a [`validation-3-6`](./validation-3-6.md) (FE-3.6).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla. P1 y P2 son de la máquina (código 3); P3 y P4, de otros
lotes (código 2, lote `Bloqueado`).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Dispositivo físico y Gradle | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios), `ro.kernel.qemu` distinto de `1` y `./gradlew --version` con salida 0. Si no → 3 |
| P2 | Credenciales de admin para crear el lugar de prueba | `POST /v1/auth/login` con las credenciales de admin responde 200 (con `401`: código 3) |
| P3 | `FE-1.1` en «Hecho»: cliente HTTP contra `dev` | Fila de `FE-1.1` en `PLAN.md` §3 = `Hecho` y `GET /v1/health` responde 200 |
| P4 | `BE-3.1` en «Hecho»: lugares | Fila en `BACKEND_FASTAPI/docs/PLAN.md` §3 = `Hecho`; `GET /v1/places` responde 200 con ≥ 1 lugar |

## 2. Comprobaciones automáticas

Instala el APK con `./gradlew installDebug` (conserva los datos de la app).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | **Paso guiado:** pide abrir Selección de destino (por voz «dos» o con la acción de TalkBack «Ir a un lugar») y espera Enter. Lee la lista con `uiautomator dump`, desplazándola con `adb shell input swipe` hasta el final, y la compara con `GET /v1/places` | Los nombres de las filas (`FilaLugar`) son exactamente los de `items[].nombre`, sin faltantes ni sobrantes, e incluye `validacion-3-1-lugar` (§4) |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C2 | Desde Inicio abre el mapa público (ruta `mapa`, `MapaPublicoScreen`) con el comando de voz «mapa»; vuelve con Atrás; lo abre otra vez con TalkBack activo y la acción «Ver mapa»; en el mapa fija un punto de inicio y pulsa ▶ | Video corto con audio: las dos formas abren el mapa, la posición empieza en el punto tocado y Atrás vuelve a Inicio |

## 4. Datos de prueba y limpieza

Crea con la API el lugar `validacion-3-1-lugar` (`POST /v1/admin/places`, categoría `bloque`, junto al primer lugar de
`GET /v1/places`). Al terminar, también si algo falló, lo borra con `DELETE /v1/admin/places/{id}`; al empezar, borra
los restos de una ejecución anterior (`GET /v1/admin/places?q=validacion-3-1`). En el teléfono no usa `pm clear`.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate31.py --entorno dev
```

Variables: `VALIDACION_API_URL`, `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` (`ARCHITECTURE.md` §5.11)
y `ANDROID_SERIAL` si hay varios dispositivos. Duración aproximada: 5 minutos, más 5 de la manual C2. El detalle de
§5 (variables de WSL, preparación numerada y salida esperada, como `validation-1-2` §5) lo escribe el lote al
implementar el validador.
