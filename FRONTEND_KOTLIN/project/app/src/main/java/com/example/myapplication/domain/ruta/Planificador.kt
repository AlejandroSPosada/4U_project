package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.model.LugarDestino
import com.google.gson.JsonArray
import com.google.gson.JsonObject

/**
 * Una ruta calculada desde la posición de la persona hasta la entrada más cercana del destino.
 *
 * - [destino]: el nombre que se dice («Has llegado a <destino>.»); [entrada]: el nodo de llegada.
 * - [inicio]: el punto proyectado sobre la arista más cercana (nodo virtual de partida).
 * - [metrosAlCamino]: distancia en línea recta de la persona a [inicio]; [fueraDelCamino] = mayor que
 *   [ParametrosRuta.fueraDelCaminoM] (la primera instrucción es [TipoInstruccion.IR_AL_CAMINO]).
 * - [metros]: la distancia **por el camino** = metros del grafo desde [inicio] hasta [entrada] (+ [metrosAlCamino] si
 *   [fueraDelCamino]).
 * - [puntos]: polilínea para dibujar, desde la posición de la persona (sin puntos repetidos).
 * - [instrucciones]: la primera ([primera]) es la que dice la vista 6.3; la última es la llegada.
 */
data class Ruta(
    val destino: String,
    val entrada: Nodo,
    val inicio: PuntoEnArista,
    val metrosAlCamino: Double,
    val fueraDelCamino: Boolean,
    val metros: Double,
    val puntos: List<PuntoRuta>,
    val instrucciones: List<Instruccion>,
) {
    val primera: Instruccion get() = instrucciones.first()

    /**
     * JSON para el mapa (`window.onNativeRuta`, ARCHITECTURE §5.9): `{"destino": "…", "metros": 85.2,
     * "puntos": [[lat, lng], …], "primera": "…"}`.
     */
    fun json(): String {
        val o = JsonObject()
        o.addProperty("destino", destino)
        o.addProperty("metros", Math.round(metros * 10.0) / 10.0)
        o.addProperty("primera", primera.texto)
        val arr = JsonArray()
        for (p in puntos) {
            val par = JsonArray()
            par.add(p.lat)
            par.add(p.lng)
            arr.add(par)
        }
        o.add("puntos", arr)
        return o.toString()
    }
}

/** [Encontrada]; [DestinoFueraDelGrafo]: ninguna entrada casa con el destino; [SinCamino]: no se llega (bloqueadas). */
sealed interface ResultadoRuta {
    data class Encontrada(val ruta: Ruta) : ResultadoRuta
    data object DestinoFueraDelGrafo : ResultadoRuta
    data object SinCamino : ResultadoRuta
}

/**
 * Fachada de FE-5.1 sobre un [Grafo] válido: entradas de un destino, proyección, ruta más corta e instrucciones
 * (ARCHITECTURE §5.7, «Grafo y rutas»; `PlanificadorTest`). Sin estado mutable: se puede llamar en cada paso.
 */
class Planificador(val grafo: Grafo, val parametros: ParametrosRuta = ParametrosRuta()) {

    /** Entradas cuyo `lugar` casa (normalizado) con alguno de [nombres]. */
    fun entradasDe(nombres: Collection<String>): List<Nodo> {
        val claves = nombres.map { EmparejarLugares.normalizar(it) }.filter { it.isNotEmpty() }.toSet()
        return grafo.entradas.filter { e -> e.lugar?.let { EmparejarLugares.normalizar(it) in claves } == true }
    }

    fun entradasDe(destino: LugarDestino): List<Nodo> = entradasDe(listOf(destino.nombre) + destino.alias)

    /** Ruta al lugar del backend [destino] (por su nombre y sus alias); dice su `nombre` al llegar. */
    fun calcular(lat: Double, lng: Double, destino: LugarDestino, rumbo: Double?): ResultadoRuta =
        calcular(lat, lng, listOf(destino.nombre) + destino.alias, destino.nombre, rumbo)

    /** La ruta a [destino] o `null` (fuera del grafo o sin camino). */
    fun rutaA(destino: LugarDestino, lat: Double, lng: Double, rumbo: Double?): Ruta? =
        (calcular(lat, lng, destino, rumbo) as? ResultadoRuta.Encontrada)?.ruta

    /**
     * Ruta desde ([lat], [lng]) a la entrada más cercana (por el camino) de las que casan con [nombres]. [rumbo]: hacia
     * dónde mira la persona (norte verdadero) o `null` (la primera instrucción no da dirección).
     */
    fun calcular(lat: Double, lng: Double, nombres: Collection<String>, nombreDestino: String, rumbo: Double?): ResultadoRuta {
        val entradas = entradasDe(nombres)
        if (entradas.isEmpty()) return ResultadoRuta.DestinoFueraDelGrafo
        val inicio = Proyeccion.masCercana(grafo, lat, lng) ?: return ResultadoRuta.SinCamino
        val camino = CalculoRuta.masCorta(grafo, inicio, entradas.map { it.id }.toSet())
            ?: return ResultadoRuta.SinCamino
        val fuera = inicio.distanciaM > parametros.fueraDelCaminoM

        val porCamino = mutableListOf(PuntoRuta(inicio.lat, inicio.lng, 0.0))
        camino.nodos.forEachIndexed { i, n ->
            val m = if (i == 0) {
                if (n.id == inicio.arista.a) inicio.metrosHastaA else inicio.metrosHastaB
            } else {
                metrosEntre(camino.nodos[i - 1].id, n.id)
            }
            porCamino += PuntoRuta(n.lat, n.lng, m)
        }
        val camino1 = sinRepetidos(porCamino)
        val dibujo = sinRepetidos(
            listOf(PuntoRuta(lat, lng, 0.0), PuntoRuta(inicio.lat, inicio.lng, inicio.distanciaM)) + porCamino.drop(1),
        )
        val instrucciones = Instrucciones.generar(
            puntos = if (fuera) dibujo else camino1,
            rumboActual = rumbo,
            alCamino = fuera && dibujo.size >= 2,
            destino = nombreDestino,
            p = parametros,
        )
        return ResultadoRuta.Encontrada(
            Ruta(
                destino = nombreDestino,
                entrada = camino.entrada,
                inicio = inicio,
                metrosAlCamino = inicio.distanciaM,
                fueraDelCamino = fuera,
                metros = camino.metros + if (fuera) inicio.distanciaM else 0.0,
                puntos = dibujo,
                instrucciones = instrucciones,
            ),
        )
    }

    private fun metrosEntre(a: String, b: String): Double =
        grafo.adyacencia[a].orEmpty().filter { it.otro(a) == b }.minOfOrNull { it.metros } ?: 0.0

    /** Quita los puntos a menos de [ParametrosRuta.puntoRepetidoM] del anterior (por sus metros), salvo el primero. */
    private fun sinRepetidos(puntos: List<PuntoRuta>): List<PuntoRuta> {
        val r = mutableListOf<PuntoRuta>()
        for (p in puntos) {
            if (r.isEmpty() || p.metrosDesdeAnterior >= parametros.puntoRepetidoM) r += p
        }
        return r
    }
}
