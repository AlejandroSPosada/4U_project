package com.example.myapplication.domain.guia

import com.example.myapplication.domain.model.ResultadoFrame
import com.example.myapplication.domain.ruta.Ruta

/** Por qué se descartó la posición de una foto. */
enum class MotivoDescarte(val clave: String) {
    SIN_COINCIDENCIAS("sin_coincidencias"),
    NIVEL_BAJO("nivel_bajo"),
    INCOHERENTE("incoherente"),
}

/** Qué hacer con la respuesta de `POST /v1/localize/frame`. */
sealed interface DecisionFrame {
    /** Reemplazar la posición por ([lat], [lng]); [limiteM]: el límite de coherencia que cumplió. */
    data class Aceptar(val lat: Double, val lng: Double, val limiteM: Double) : DecisionFrame

    data class Descartar(val motivo: MotivoDescarte, val limiteM: Double) : DecisionFrame
}

/**
 * Regla simple de mezcla de pasos y fotos (decisión del usuario del 2026-10-27; `ReglaMezclaTest`): los pasos mueven la
 * posición entre fotos y una foto confiable **y** coherente con lo caminado la reemplaza; si no, se descarta (una foto
 * equivocada no hace saltar la posición).
 */
object ReglaMezcla {

    /** Salto máximo admitido (m) tras [caminadoM] metros desde la última posición aceptada. */
    fun limiteCoherenciaM(caminadoM: Double, p: ParametrosGuia = ParametrosGuia()): Double =
        p.coherenciaBaseM + p.coherenciaPorMetro * caminadoM.coerceAtLeast(0.0)

    /** `radio_m` que se pide: el límite + [ParametrosGuia.margenRadioM], dentro de [radioMinM, radioMaxM]. */
    fun radioM(caminadoM: Double, p: ParametrosGuia = ParametrosGuia()): Double =
        (limiteCoherenciaM(caminadoM, p) + p.margenRadioM).coerceIn(p.radioMinM, p.radioMaxM)

    /**
     * [resultado]: la respuesta; [caminadoM]: metros caminados desde la última posición aceptada hasta el momento de la
     * foto; ([previaLat], [previaLng]): la `posicion_previa` enviada; ([actualLat], [actualLng]): la posición estimada
     * **ahora** (la persona siguió caminando mientras llegaba la respuesta).
     *
     * Al aceptar, la corrección se aplica como un desplazamiento: actual + (foto − previa); así no se pierden los pasos
     * dados durante la petición.
     */
    fun decidir(
        resultado: ResultadoFrame,
        caminadoM: Double,
        previaLat: Double,
        previaLng: Double,
        actualLat: Double,
        actualLng: Double,
        p: ParametrosGuia = ParametrosGuia(),
    ): DecisionFrame {
        val limite = limiteCoherenciaM(caminadoM, p)
        val u = resultado as? ResultadoFrame.Ubicado
            ?: return DecisionFrame.Descartar(MotivoDescarte.SIN_COINCIDENCIAS, limite)
        if (u.nivel !in p.nivelesAceptados) return DecisionFrame.Descartar(MotivoDescarte.NIVEL_BAJO, limite)
        if (u.distanciaPreviaM > limite) return DecisionFrame.Descartar(MotivoDescarte.INCOHERENTE, limite)
        return DecisionFrame.Aceptar(actualLat + (u.lat - previaLat), actualLng + (u.lng - previaLng), limite)
    }
}

/**
 * Cuándo tomar la foto de corrección (FE-5.3; `ReglaMezclaTest`): cada [ParametrosGuia.metrosEntreFotos] caminados
 * desde la anterior, o antes si la posición es dudosa (a más de [ParametrosGuia.dudosaM] de la ruta) y se caminó al
 * menos [ParametrosGuia.minMetrosEntreFotos]. Nunca con otra foto en curso.
 */
class DisparadorFoto(private val p: ParametrosGuia = ParametrosGuia(), inicioM: Double = 0.0) {
    private var ultimaM = inicioM

    fun debeTomar(caminadoM: Double, desvioM: Double, ocupado: Boolean): Boolean {
        if (ocupado) return false
        val desde = caminadoM - ultimaM
        return desde >= p.metrosEntreFotos || (desvioM >= p.dudosaM && desde >= p.minMetrosEntreFotos)
    }

    /** La foto se pidió con [caminadoM] metros caminados (cuenta aunque luego falle o se descarte). */
    fun tomada(caminadoM: Double) {
        ultimaM = caminadoM
    }
}

/**
 * Desvío: [ParametrosGuia.lecturasDesvio] lecturas seguidas a más de [ParametrosGuia.desvioM] de la ruta
 * (`GuiaNavegacionTest`). Una lectura cerca de la ruta reinicia la cuenta.
 */
class DetectorDesvio(private val p: ParametrosGuia = ParametrosGuia()) {
    var seguidas: Int = 0
        private set

    /** `true` cuando toca recalcular (y reinicia la cuenta). */
    fun lectura(desvioM: Double): Boolean {
        seguidas = if (desvioM > p.desvioM) seguidas + 1 else 0
        if (seguidas >= p.lecturasDesvio) {
            seguidas = 0
            return true
        }
        return false
    }

    fun reiniciar() {
        seguidas = 0
    }
}

/**
 * Alertas cercanas a la ruta (FE-5.3 deja el punto de conexión; lo implementa FE-3.6 con `DetectarAlertasCercanas` en
 * la fase de documentación): la guía lo llama en cada actualización de posición y dice, con prioridad, cada texto
 * devuelto. Quien lo implemente decide cuándo repetir una alerta («una vez por aproximación», 6.5).
 */
fun interface AvisadorAlertasRuta {
    /** Textos que hay que decir ahora para la persona en ([lat], [lng]), a [avanceM] metros del inicio de [ruta]. */
    fun avisos(lat: Double, lng: Double, avanceM: Double, ruta: Ruta): List<String>
}

/** Implementación vacía mientras FE-3.6 no conecte las alertas. */
object SinAvisosDeAlertas : AvisadorAlertasRuta {
    override fun avisos(lat: Double, lng: Double, avanceM: Double, ruta: Ruta): List<String> = emptyList()
}
