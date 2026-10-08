package com.example.myapplication.map

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.Closeable
import java.io.File
import java.util.zip.GZIPInputStream

/**
 * Lee `eafit.mbtiles` (tiles VECTORIALES .pbf, como en script2.py).
 *
 * El archivo se incluye en `app/src/main/assets/eafit.mbtiles`; SQLite no puede abrir
 * un asset directamente, así que se copia una vez a `filesDir/map/`.
 */
class MbtilesReader private constructor(
    private val db: SQLiteDatabase,
    val minZoom: Int,
    val maxZoom: Int,
    /** [oeste, sur, este, norte] en lon/lat. */
    val limites: DoubleArray,
) : Closeable {

    /** Devuelve el tile .pbf ya descomprimido, o null si no existe. */
    fun tile(z: Int, x: Int, y: Int): ByteArray? {
        val filaTms = (1 shl z) - 1 - y // MBTiles usa TMS: el eje Y va invertido
        db.rawQuery(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            arrayOf(z.toString(), x.toString(), filaTms.toString()),
        ).use { c ->
            if (!c.moveToFirst()) return null
            return descomprimir(c.getBlob(0))
        }
    }

    /** JSON que consume editor_mapa.html para construir el estilo y encuadrar el campus. */
    fun metaJson(): String = JSONObject()
        .put("minzoom", minZoom)
        .put("maxzoom", maxZoom)
        .put("bounds", JSONArray().apply { limites.forEach { put(it) } })
        .toString()

    override fun close() = db.close()

    companion object {
        private const val ASSET = "eafit.mbtiles"
        private const val ARCHIVO = "map/eafit.mbtiles"
        private const val PREFS = "mapa"
        private const val CLAVE_COPIADO = "mbtiles_copiado_en"

        suspend fun abrir(context: Context): MbtilesReader = withContext(Dispatchers.IO) {
            val archivo = copiarSiHaceFalta(context)
            val db = SQLiteDatabase.openDatabase(archivo.path, null, SQLiteDatabase.OPEN_READONLY)

            val meta = HashMap<String, String>()
            db.rawQuery("SELECT name, value FROM metadata", null).use { c ->
                while (c.moveToNext()) meta[c.getString(0)] = c.getString(1)
            }
            val b = meta["bounds"]?.split(",")?.mapNotNull { it.trim().toDoubleOrNull() }
            MbtilesReader(
                db = db,
                minZoom = meta["minzoom"]?.toIntOrNull() ?: 0,
                maxZoom = meta["maxzoom"]?.toIntOrNull() ?: 18,
                limites = if (b != null && b.size == 4) b.toDoubleArray()
                else doubleArrayOf(-180.0, -85.0, 180.0, 85.0),
            )
        }

        @Suppress("DEPRECATION")
        private fun copiarSiHaceFalta(context: Context): File {
            val destino = File(context.filesDir, ARCHIVO)
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            // Se vuelve a copiar cuando la app se actualiza (por si cambió el mapa incluido).
            val instalacion = context.packageManager
                .getPackageInfo(context.packageName, 0).lastUpdateTime

            if (!destino.exists() || prefs.getLong(CLAVE_COPIADO, 0L) != instalacion) {
                destino.parentFile?.mkdirs()
                val tmp = File(destino.parentFile, "$ASSET.tmp")
                context.assets.open(ASSET).use { entrada ->
                    tmp.outputStream().use { salida -> entrada.copyTo(salida) }
                }
                destino.delete()
                check(tmp.renameTo(destino)) { "No se pudo instalar $ASSET" }
                prefs.edit().putLong(CLAVE_COPIADO, instalacion).apply()
            }
            return destino
        }

        private fun descomprimir(datos: ByteArray): ByteArray {
            val esGzip = datos.size > 2 &&
                datos[0] == 0x1f.toByte() && datos[1] == 0x8b.toByte()
            return if (esGzip) GZIPInputStream(datos.inputStream()).use { it.readBytes() } else datos
        }
    }
}