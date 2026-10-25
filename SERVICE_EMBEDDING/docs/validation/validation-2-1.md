# Validación 2-1 — EMB-2.1 Vectorización por lotes

| Campo | Valor |
|---|---|
| Lote | `EMB-2.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate21.py` |
| Entornos | `local` (**cierra el lote**, con `EMBEDDING_IMAGEN` = la imagen que `embedding.yml` publicó en ECR para el commit que se cierra). `dev` no aplica: el servicio es privado y §5.8 reserva `dev` para arranque y rendimiento |
| Criterios | Automáticos: C1, C2, C3, C4, C5 (C5a, C5b, C5c) · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.8. El diseño que se valida está en ARCHITECTURE §4.3 (cola con prioridad e hilo único), §5.2
(`POST /v1/embed`), §5.3 (pp-v1), §5.4 (vectores dorados y tolerancia), §5.6 (errores) y §5.7 (parámetros), y en
ADR-EMB-07 (una inferencia a la vez) y ADR-EMB-12 (dónde se calculan los dorados).

## 1. Precondiciones

El script las evalúa en orden y, si una falla, no sigue. P1: código 3 si falta Docker o el puerto 8080 está ocupado.
P2: código 3 sin la variable o con el `pull` fallido; 2 si la imagen no es `linux/amd64`. P3: código 3 si `docker run`
falla; 2 (EMB-1.1 no está «Hecho») si la imagen no queda lista o no publica su `version_vector`.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Docker disponible y puerto 8080 libre | `docker info` con código 0; borra el contenedor de una ejecución anterior (§4) y después una conexión a `localhost:8080` es rechazada |
| P2 | `EMBEDDING_IMAGEN` definida y de plataforma `linux/amd64` (infra §5.9) | Si es de ECR, `docker login` con el token de `ecr:GetAuthorizationToken` (necesita `AWS_PROFILE`) y `docker pull`; si es local, `docker pull` solo si no existe. Después `docker image inspect --format '{{.Os}}/{{.Architecture}}'` = `linux/amd64` |
| P3 | `EMB-1.1` en «Hecho»: la imagen arranca, queda lista y publica su `version_vector` | `docker run -d --name validacion-emb21 -p 8080:8080 -e TORCH_NUM_THREADS=1 $EMBEDDING_IMAGEN`; `GET http://localhost:8080/health/ready` = 200 `{"estado": "listo"}` antes de 180 s; `GET /v1/info` → `version_vector = dinov2-vits14/pp-v1` y `lote_max = 8`. Si el contenedor se detiene antes, falla con las últimas líneas de su log |

## 2. Comprobaciones automáticas

Orden: C1, C2, C3, C4, C5a, C5b, C5c. Todas las peticiones van a `POST http://localhost:8080/v1/embed` en
`multipart/form-data` con partes `imagenes` (archivo `validacion-emb21-<n>-<i>`), llevan
`X-Request-Id: validacion-emb21-<n>` y, salvo que se indique, no envían `X-Prioridad` (= `baja`). Cada comprobación
espera todas sus respuestas antes de la siguiente, así que C4 y C5c empiezan con la cola vacía. Los parámetros de §5.7
(`LOTE_MAX`, `BYTES_MAX_*`, `COLA_MAX_IMAGENES`, `RETRY_AFTER_S`) son los valores por defecto de `config.py`; una prueba
de `test_ops_comun.py` comprueba que el script usa los mismos.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | Lee `project/tests/golden/esperados.json` y comprueba que las cinco imágenes del directorio son las de su `sha256` (si no, falla). Envía sola cada una (`image/jpeg` o `image/png` según el archivo) y compara la respuesta con su vector esperado | Las cinco responden `200` con `version_vector = dinov2-vits14/pp-v1`, `dim = 384` y 384 componentes, y la diferencia máxima por componente es ≤ 1e-5 |
| C2 | Una petición con 8 partes (las 5 doradas y 3 sintéticas JPEG de 640 × 480 con semilla fija) y cada una de esas 8 imágenes sola | Para las 8, `vectores[i]` del lote y el vector de la imagen enviada sola difieren ≤ 1e-5 por componente |
| C3 | Una petición con 4 partes válidas salvo la tercera: `image/jpeg` con bytes no decodificables (la primera mitad de un JPEG) | `400`, `error.codigo = IMAGEN_INVALIDA` y `error.detalle.indice = 2` |
| C4 | Mide la duración `T` de un lote de 8 en esa máquina (`tiempos_ms.inferencia` de una petición de 8 sintéticas). Después suelta a la vez, con una barrera, 4 peticiones `baja` de 8 imágenes sintéticas (33 imágenes con la `alta`, por debajo de `COLA_MAX_IMAGENES` = 40 aunque cuente el lote en curso) y, `T`/2 después (entre 0,05 y 1 s: a mitad del primer lote), una con `X-Prioridad: alta` y 1 imagen. Para cada petición calcula su salida de la cola = instante de envío + `tiempos_ms.cola`. Un intento es válido si (a) al menos 2 `baja` salen de la cola después del envío de la `alta` (seguían esperando; no cuentan las que salen en los primeros min(0,1 s, `T`/4), mientras la `alta` todavía sube); si no, la máquina fue más rápida de lo medido y se repite con la mitad de espera, hasta 3 intentos | En un intento válido: (b) la `alta` sale de la cola antes que todas las `baja` que esperaban; (c) su `tiempos_ms.cola` ≤ `tiempos_ms.inferencia` de la `baja` en curso (la que salió de la cola justo antes) + 500 ms (solo espera ese lote, §4.3). Falla si alguna petición no responde `200`, si (b) o (c) no se cumplen o si ningún intento es válido |
| C5a | Tres peticiones: 9 partes JPEG pequeñas; 1 parte PNG de ruido de 1300 × 1300 (~4,8 MB, más de 4 MB); 5 partes PNG de ruido de 1100 × 1100 (~3,5 MB cada una, ~17 MB en total) | Las tres responden `413` con `error.codigo = LOTE_DEMASIADO_GRANDE` |
| C5b | Una petición con 1 parte `image/gif` sintética | `415` con `error.codigo = TIPO_NO_SOPORTADO` |
| C5c | Suelta a la vez, con una barrera, 8 peticiones `baja` de 8 imágenes sintéticas (64 imágenes frente a `COLA_MAX_IMAGENES` = 40). Si ninguna se rechaza (las primeras terminaron antes de que llegaran las últimas), repite, hasta 3 intentos | Al menos una responde `503` con `error.codigo = SATURADO` y encabezado `Retry-After: 5` (`RETRY_AFTER_S`, §5.7); el resto, `200` con 8 vectores. Falla con cualquier otra respuesta o si en 3 intentos la cola nunca se satura |

**Por qué C4 y C5c no dependen de la velocidad de la máquina.** C4 no espera un tiempo fijo: lanza la `alta` a mitad
del primer lote, con la duración medida en esa misma máquina, y un intento en el que la máquina corre más de lo medido
no cuenta como fallo, sino que se repite. (b) compara salidas de la cola separadas al menos por la inferencia de la
`alta` (unos 0,1–0,2 s por imagen en CPU) y (c) usa solo tiempos que mide el servicio. C5c necesita que 7 de las 8
peticiones lleguen mientras se calcula la primera: las sube a la vez (unos 0,3 MB cada una, en `localhost`) y un lote de
8 tarda al menos varios cientos de milisegundos en CPU. El script se ensayó contra el servicio con el modelo real y
`TORCH_NUM_THREADS=1`, y con un modelo falso de 8 s y de 0,07 s por lote de 8; pasó en los tres casos al primer intento.

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

El servicio no guarda nada (§5.8). El script usa las cinco imágenes de `project/tests/golden/` e imágenes sintéticas que
genera en memoria con semilla fija (JPEG de 640 × 480 y de 128 × 96, PNG de ruido para los límites de tamaño, un GIF
para C5b y un JPEG truncado para C3); no escribe nada en disco salvo el informe. El único recurso es el contenedor
`validacion-emb21`: al terminar (también si algo falló, salvo `--sin-limpieza`) lo borra con `docker rm -f`, y al
empezar borra el que haya quedado de una ejecución anterior con ese nombre.

## 5. Cómo ejecutarlo

```bash
cd SERVICE_EMBEDDING/project
EMBEDDING_IMAGEN=<ecr_embedding_url>:<sha> uv run --group ops python src/ops/validate21.py --entorno local
```

Variables: `EMBEDDING_IMAGEN` (§5.8); `AWS_PROFILE` solo si la imagen es de ECR (`ecr:GetAuthorizationToken`,
`BatchGetImage` y `GetDownloadUrlForLayer` sobre `campus-locator/embedding`). En la máquina: `uv`, `git` (commit del
informe) y Docker. No toca AWS más allá de descargar la imagen, así que vale a cualquier hora y con `embedding`
encendido o apagado. Duración aproximada: 2–5 min (arranque de hasta 3 min y unos 15 lotes de 8 imágenes entre C2, C4 y
C5c). El informe queda en `project/.validacion/EMB-2.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) salvo que se indique
`--informe`.

**Preparación.**

1. Pruebas y estilo, con `uv.lock` al día (Pillow y `python-multipart` entraron en EMB-2.1). Con los pesos en
   `project/.modelo/` o en `MODELO_DIR` (cómo copiarlos de la imagen: `tools/dorados.py`), `test_dorados.py` compara
   también los vectores dorados; `DORADOS_OBLIGATORIOS=1` hace que fallen, en vez de omitirse, si no los encuentra:
   ```bash
   cd SERVICE_EMBEDDING/project
   uv sync --locked
   uv run ruff check . && uv run ruff format --check . && DORADOS_OBLIGATORIOS=1 uv run pytest
   ```
2. Llevar el commit a `main` (PR o *push*). `embedding.yml` pasa las pruebas, publica
   `…/campus-locator/embedding:<SHA>` y registra la revisión; con el servicio apagado no espera (§4.2).
3. `EMBEDDING_IMAGEN` = la imagen de ese commit:
   ```bash
   SHA=$(git rev-parse HEAD)
   aws ecr describe-images --region us-east-1 --repository-name campus-locator/embedding \
     --image-ids imageTag=$SHA --query 'imageDetails[0].imageTags' --output text
   ```
   Esperado: el SHA. `EMBEDDING_IMAGEN=648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:$SHA`.

Para probar antes de que haya imagen en ECR (no cierra el lote), se construye desde `project/` con
`docker build --platform linux/amd64 --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t campus-locator/embedding:local .`
y se usa `EMBEDDING_IMAGEN=campus-locator/embedding:local`.

Esperado al ejecutar: código 0, con `[PASA]` en P1–P3 y en C1, C2, C3, C4, C5a, C5b y C5c. Con eso, la fila EMB-2.1 de
PLAN §3 pasa a «Hecho» con el commit, la fecha y la versión de ARCHITECTURE.
