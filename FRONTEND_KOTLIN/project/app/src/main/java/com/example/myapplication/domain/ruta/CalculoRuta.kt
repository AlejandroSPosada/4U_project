package com.example.myapplication.domain.ruta

import java.util.PriorityQueue

/**
 * Camino más corto por el grafo desde un [inicio] (punto proyectado) hasta una [entrada]. [nodos] va del primer nodo
 * del grafo que se alcanza (un extremo de la arista de [inicio]) a la [entrada]; [metros] es la longitud por el grafo
 * desde el punto proyectado (con los metros declarados; sin el tramo de la persona hasta el camino).
 */
data class Camino(
    val inicio: PuntoEnArista,
    val nodos: List<Nodo>,
    val metros: Double,
    val entrada: Nodo,
)

/**
 * Ruta más corta (Dijkstra) en el teléfono, sin red (FE-5.1; `CalculoRutaTest`). El nodo virtual de partida es el
 * punto proyectado: se conecta con los dos extremos de su arista con `t · metros` y `(1 − t) · metros`. Solo se usan
 * aristas no `bloqueada`. Con varios destinos (un lugar con varias entradas) gana el más cercano por el camino; un empate
 * exacto se decide por el id del nodo (resultado estable).
 */
object CalculoRuta {

    fun masCorta(grafo: Grafo, inicio: PuntoEnArista, destinos: Set<String>): Camino? {
        if (destinos.isEmpty()) return null
        val dist = HashMap<String, Double>()
        val previo = HashMap<String, String?>()
        val cola = PriorityQueue<Pair<Double, String>>(compareBy<Pair<Double, String>> { it.first }.thenBy { it.second })

        fun relajar(id: String, d: Double, desde: String?) {
            val actual = dist[id]
            if (actual == null || d < actual) {
                dist[id] = d
                previo[id] = desde
                cola.add(d to id)
            }
        }

        relajar(inicio.arista.a, inicio.metrosHastaA, null)
        relajar(inicio.arista.b, inicio.metrosHastaB, null)
        val cerrados = HashSet<String>()
        var llegada: String? = null
        while (cola.isNotEmpty()) {
            val (d, id) = cola.poll()!!
            if (!cerrados.add(id)) continue
            if (d > (dist[id] ?: Double.MAX_VALUE)) continue
            if (id in destinos) {
                llegada = id
                break
            }
            for (ar in grafo.adyacencia[id].orEmpty()) {
                val otro = ar.otro(id) ?: continue
                if (otro in cerrados) continue
                relajar(otro, d + ar.metros, id)
            }
        }
        val fin = llegada ?: return null
        val ids = ArrayDeque<String>()
        var cursor: String? = fin
        while (cursor != null) {
            ids.addFirst(cursor)
            cursor = previo[cursor]
        }
        val nodos = ids.mapNotNull { grafo.porId[it] }
        return Camino(inicio, nodos, dist.getValue(fin), grafo.porId.getValue(fin))
    }
}
