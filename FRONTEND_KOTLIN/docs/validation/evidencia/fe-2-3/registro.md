# Registro de pruebas en dispositivo — FE-2.3 C3

Decisión del usuario (2026-10-26): C3 se valida **en casa**, no en el campus, y solo en lo que se pudo comprobar allí:
que el detector cuenta los pasos. El tramo A→B se marcó en el mapa sin medirlo en el terreno, así que la longitud
guardada (0,71 m) es **provisional**: antes de grabar el dataset hay que recalibrar 7.3b en un tramo recto medido, con
el mismo teléfono con el que se grabe (la calibración vive en ese teléfono). El disparo cada 5 m lo cubre la prueba
automática `DisparadorCapturaTest` (C1). Evidencia: captura de 7.3b vista por el maestro (no se versiona: muestra la
zona del mapa marcada por el usuario).

| Fecha | Modelo | Android | Prueba | Recorrido | Pasos | `distanciaMetros` | Longitud guardada (`fecha_ms`) | Fotos frente a `5 / longitud` | Error final medido | Notas |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-26 | Redmi Note 15 Pro | sin anotar | 7.3b | Tramo A→B de 7,1 m marcado en el mapa (en casa, sin medir en el terreno) | 10 | — | 0,71 m (provisional; 7,1 m ÷ 10 pasos) | — | — | El usuario confirma que el detector contó sus pasos reales. Antes se usaba la genérica (0,72 m) |
| 2026-10-26 | Redmi Note 15 Pro | sin anotar | 7.4 | Recorrido `rec_0017` en casa, «Cada 3 s» (FE-2.1) | — | 15 m (pantalla de 7.13) | 0,71 m | — (modo tiempo, no distancia) | — | Sirvió para FE-2.1; no es un recorrido conocido |
| — | — | — | PDR (mapa público) y 7.3 en un recorrido conocido de ≥ 100 m | **No se hizo** (decisión del usuario) | — | — | — | — | — | Queda para la primera salida de grabación del dataset |
