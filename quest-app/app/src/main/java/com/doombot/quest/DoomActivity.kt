package com.doombot.quest

import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.ComposeView
import com.doombot.quest.ui.Hud
import com.doombot.quest.ui.PanelAjustes
import com.doombot.quest.ui.PanelApps
import com.doombot.quest.ui.PanelBrazalete
import com.doombot.quest.ui.PanelChat
import com.doombot.quest.ui.PanelInfo
import com.doombot.quest.ui.PanelOrbe
import com.doombot.quest.ui.PanelSistema
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Query
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.isdk.IsdkPanelGrabHandle
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.AvatarBody
import com.meta.spatial.toolkit.CylinderShapeOptions
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.UIPanelShapeOptions
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.toolkit.createPanelEntity
import com.meta.spatial.vr.LocomotionSystem
import com.meta.spatial.vr.VRFeature
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * D.O.O.M en realidad mixta: el orbe en el centro y los paneles alrededor, en tu habitacion.
 *
 * Todo lo que se ve es un panel de Compose en una entidad con ``Grabbable``: con la mano (pellizco
 * y arrastrar) o el mando se coge y se deja donde se quiera, y los botones se pulsan igual. Cada
 * ventana se puede minimizar, curvar y cambiar de tamaño, y el brazalete de la muñeca izquierda
 * las maneja todas. La escena se construye en codigo, sin Spatial Editor (ver D-041).
 */
class DoomActivity : AppSystemActivity(), Controlador.Escena {

  private val ambito = CoroutineScope(Dispatchers.Main)
  private val ctl by lazy { Controlador(this, this) }
  private val ventanas = HashMap<Ventana, Entity>()
  /** Donde estaba cada ventana al minimizarla o curvarla: al volver, aparece en el mismo sitio. */
  private val poses = HashMap<Ventana, Pose>()
  private val infos = HashMap<Int, Entity>()
  private var brazalete: Entity? = null
  private var lista = false
  private var alConceder: ((Boolean) -> Unit)? = null
  private val huecosInfo = listOf(R.id.panel_info_0, R.id.panel_info_1, R.id.panel_info_2)

  /** Donde va cada panel respecto a la cabeza: angulo (grados), distancia (m), altura relativa (m). */
  private data class Sitio(val angulo: Float, val distancia: Float, val altura: Float)

  private val sitios =
      mapOf(
          Ventana.ORBE to Sitio(0f, 1.0f, -0.12f),
          Ventana.SISTEMA to Sitio(36f, 1.05f, -0.10f),
          Ventana.REGISTRO to Sitio(-36f, 1.05f, -0.10f),
          Ventana.APPS to Sitio(0f, 0.95f, -0.66f),
          Ventana.AJUSTES to Sitio(0f, 0.78f, -0.06f),
      )
  // Los de informacion aparecen delante, un poco escalonados, y se mueven con la mano.
  private val sitiosInfo = listOf(Sitio(18f, 0.85f, 0.18f), Sitio(-18f, 0.85f, 0.18f), Sitio(0f, 0.85f, 0.32f))

  // Las manos (ISDK: pellizcar, coger, pulsar) las registra ya VRFeature desde el SDK 0.14: añadir
  // IsdkFeature a mano esta obsoleto y lo duplicaria.
  override fun registerFeatures(): List<SpatialFeature> = listOf(VRFeature(this), ComposeFeature())

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    systemManager.findSystem<LocomotionSystem>().enableLocomotion(false)
    scene.enablePassthrough(true)
    systemManager.registerSystem(SeguirSistema())
    systemManager.registerSystem(BrazaleteSistema())
    ctl.arrancar()
  }

  override fun onSceneReady() {
    super.onSceneReady()
    // La pose de la cabeza tarda unos instantes en ser real: se espera antes de colocar nada.
    ambito.launch {
      delay(900)
      lista = true
      Ventana.entries.forEach { mostrarVentana(it) }
      brazalete = Entity.createPanelEntity(R.id.panel_brazalete, Transform(Pose(Vector3(0f, -50f, 0f))), Visible(false))
      if (Doom.conClave.isEmpty()) ctl.abrirAjustes() // primera vez: directo a configurar
    }
  }

  override fun registerPanels(): List<PanelRegistration> {
    val contenido: Map<Ventana, @Composable () -> Unit> =
        mapOf(
            Ventana.ORBE to { PanelOrbe(ctl) },
            Ventana.SISTEMA to { PanelSistema(ctl) },
            Ventana.REGISTRO to { PanelChat(ctl) },
            Ventana.APPS to { PanelApps(ctl) },
            Ventana.AJUSTES to { PanelAjustes(ctl) },
        )
    // Cada ventana, plana y curva. El cilindro tiene el radio de la distancia a la que se pone:
    // asi la curva "abraza" al usuario y todo el panel queda a la misma distancia de los ojos.
    val principales =
        Ventana.entries.flatMap { v ->
          listOf(
              panel(v.plana, QuadShapeOptions(width = v.ancho, height = v.alto)) { contenido.getValue(v)() },
              panel(v.curva, CylinderShapeOptions(radius = sitios.getValue(v).distancia, width = v.ancho, height = v.alto)) {
                contenido.getValue(v)()
              },
          )
        }
    // El brazalete: pequeño y con mas densidad, porque se mira de cerca (a unos 35 cm).
    val brazo = panel(R.id.panel_brazalete, QuadShapeOptions(width = 0.20f, height = 0.27f), dpPorMetro = 1400f) { PanelBrazalete(ctl) }
    return principales + brazo + huecosInfo.mapIndexed { n, id -> panel(id, QuadShapeOptions(width = 0.40f, height = 0.34f)) { PanelInfo(ctl, n) } }
  }

  private fun panel(id: Int, forma: UIPanelShapeOptions, dpPorMetro: Float = 800f, contenido: @Composable () -> Unit) =
      ComposeViewPanelRegistration(
          id,
          composeViewCreator = { _, contexto ->
            ComposeView(contexto).apply {
              setContent { MaterialTheme(colorScheme = darkColorScheme(primary = Hud.c1)) { contenido() } }
            }
          },
          settingsCreator = {
            UIPanelSettings(
                shape = forma,
                style = PanelStyleOptions(themeResourceId = R.style.PanelTransparente),
                // 800 dp por metro: texto nitido y de tamaño comodo a un metro.
                display = DpPerMeterDisplayOptions(dpPerMeter = dpPorMetro),
            )
          },
      )

  // -- colocar en la habitacion -------------------------------------------------------------
  private fun poseDelante(sitio: Sitio): Pose {
    val cabeza = scene.getViewerPose()
    val adelante = horizontal(cabeza.forward())
    val dir = Quaternion.fromAxisAngle(Vector3.Up, sitio.angulo).times(adelante).normalize()
    val altura = if (cabeza.t.y < 0.3f) 1.35f else cabeza.t.y // sin seguimiento aun: altura de pie
    val pos = Vector3(cabeza.t.x, altura + sitio.altura, cabeza.t.z) + dir * sitio.distancia
    return Pose(pos, Quaternion.lookRotationAroundY(dir))
  }

  /**
   * Pone la ventana como dice su estado. Si ya existe con la forma buena, solo cambia el tamaño;
   * si cambia de forma (plana/curva), se rehace en el mismo sitio; minimizada, se quita y se
   * recuerda donde estaba.
   */
  override fun mostrarVentana(v: Ventana) {
    if (!lista) return
    val estado = Doom.ventana(v)
    val actual = ventanas[v]
    if (!estado.abierta) {
      actual?.let { poses[v] = it.getComponent<Transform>().transform; it.destroy() }
      ventanas.remove(v)
      return
    }
    val id = if (estado.curva) v.curva else v.plana
    if (actual != null && formas[v] == id) {
      actual.setComponent(Scale(Vector3(estado.escala, estado.escala, estado.escala)))
      return
    }
    actual?.let { poses[v] = it.getComponent<Transform>().transform; it.destroy() }
    val pose = poses[v] ?: poseDelante(sitios.getValue(v))
    ventanas[v] = crearPanel(id, pose, estado.escala)
    formas[v] = id
  }

  private val formas = HashMap<Ventana, Int>()

  /**
   * Una ventana en la habitacion. Con las asas de Meta (experimental), el SDK pone su barra para
   * moverla y las esquinas para redimensionarla; sin ellas, se coge entera con ``Grabbable``.
   */
  private fun crearPanel(id: Int, pose: Pose, escala: Float): Entity {
    // PIVOT_Y: al moverlo sigue derecho y mirandote, que es lo que se espera de una pantalla.
    val e = Entity.createPanelEntity(id, Transform(pose), Grabbable(type = GrabbableType.PIVOT_Y), Scale(Vector3(escala, escala, escala)))
    if (Doom.esquinas) e.setComponent(IsdkPanelGrabHandle())
    return e
  }

  override fun rehacerVentanas() {
    if (!lista) return
    Ventana.entries.forEach { v ->
      ventanas.remove(v)?.let { poses[v] = it.getComponent<Transform>().transform; it.destroy() }
      formas.remove(v)
      mostrarVentana(v)
    }
  }

  override fun recolocar() {
    poses.clear()
    for ((v, e) in ventanas) e.setComponent(Transform(poseDelante(sitios.getValue(v))))
    Doom.anotar(TipoLinea.COMENTARIO, "Todo delante de usted, Mi Señor.")
  }

  override fun mostrarInfo(n: Int, visible: Boolean) {
    val id = huecosInfo.getOrNull(n) ?: return
    infos.remove(n)?.destroy() // si ya estaba, vuelve a aparecer delante con lo nuevo
    if (visible) infos[n] = crearPanel(id, poseDelante(sitiosInfo[n]), 1f)
  }

  // -- permisos -----------------------------------------------------------------------------
  /** Micro y camara se piden al usarlos, no al arrancar. Se responde con todos concedidos o no. */
  override fun pedirPermisos(permisos: Array<String>, alTerminar: (Boolean) -> Unit) {
    val faltan = permisos.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
    if (faltan.isEmpty()) {
      alTerminar(true)
      return
    }
    alConceder?.invoke(false) // una peticion anterior sin responder se da por denegada
    alConceder = alTerminar
    requestPermissions(faltan.toTypedArray(), PERMISOS)
  }

  @Deprecated("Deprecated in Java")
  override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
    super.onRequestPermissionsResult(requestCode, permissions, grantResults)
    if (requestCode != PERMISOS) return
    val todos = grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }
    alConceder?.invoke(todos)
    alConceder = null
  }

  override fun onDestroy() {
    ctl.cerrar()
    super.onDestroy()
  }

  /**
   * "Seguirme": el orbe te acompaña con pereza. Solo se mueve cuando se ha quedado atras (como un
   * HUD que no tiembla con cada giro de cabeza), y se acerca poco a poco.
   */
  private inner class SeguirSistema : SystemBase() {
    override fun execute() {
      if (!Doom.orbeSigue) return
      val orbe = ventanas[Ventana.ORBE] ?: return
      val objetivo = poseDelante(sitios.getValue(Ventana.ORBE))
      val actual = orbe.getComponent<Transform>().transform
      val distancia = (objetivo.t - actual.t).length()
      if (distancia < 0.25f) return
      val pos = actual.t + (objetivo.t - actual.t) * 0.06f
      orbe.setComponent(Transform(Pose(pos, objetivo.q)))
    }
  }

  /**
   * El brazalete: sobre la muñeca izquierda, mirandote, como un reloj. Aparece al levantar la
   * muñeca y mirarla (o siempre, si esta fijado) y se esconde al bajarla, para no estorbar. La
   * mano sale del ``AvatarBody`` del jugador; con mandos, es la del mando izquierdo.
   */
  private inner class BrazaleteSistema : SystemBase() {
    private var cuerpo: Entity? = null
    private var visibleHasta = 0L
    private var mostrado = false

    override fun execute() {
      val b = brazalete ?: return
      val mano = manoIzquierda()
      val cabeza = scene.getViewerPose()
      val ahora = System.currentTimeMillis()
      var pose: Pose? = null
      if (mano != null && mano.t.length() > 0.01f) {
        val haciaMano = mano.t - cabeza.t
        val distancia = haciaMano.length()
        val mirando = distancia in 0.12f..0.75f && cabeza.forward().normalize().dot(haciaMano.normalize()) > (if (mostrado) 0.55f else 0.8f)
        if (mirando) visibleHasta = ahora + 900 // un margen al apartar la vista, para poder pulsar
        // Un poco por encima de la muñeca y hacia los ojos, girado hacia la cara.
        val pos = mano.t + Vector3(0f, 0.11f, 0f) + (cabeza.t - mano.t).normalize() * 0.03f
        pose = Pose(pos, Quaternion.lookRotationAroundY(horizontal(pos - cabeza.t)))
      } else if (Doom.brazaleteFijo) {
        // Sin mano a la vista: fijado, abajo a la izquierda delante de ti.
        val pos = cabeza.t + horizontal(cabeza.forward()) * 0.45f + Vector3(0f, -0.25f, 0f) +
            Quaternion.fromAxisAngle(Vector3.Up, 90f).times(horizontal(cabeza.forward())) * 0.18f
        pose = Pose(pos, Quaternion.lookRotationAroundY(horizontal(pos - cabeza.t)))
      }
      val ver = pose != null && (Doom.brazaleteFijo || ahora < visibleHasta)
      if (ver) {
        b.setComponent(Transform(pose!!))
      } else if (mostrado) {
        b.setComponent(Transform(Pose(Vector3(0f, -50f, 0f)))) // fuera de alcance: no capta pellizcos
      }
      if (ver != mostrado) {
        b.setComponent(Visible(ver))
        mostrado = ver
      }
    }

    private fun manoIzquierda(): Pose? {
      val c = cuerpo ?: Query.where { has(AvatarBody.id) }.eval().firstOrNull { it.getComponent<AvatarBody>().isPlayerControlled }?.also { cuerpo = it }
      return runCatching { c?.getComponent<AvatarBody>()?.leftHand?.getComponent<Transform>()?.transform }.getOrNull()
    }
  }

  companion object {
    private const val PERMISOS = 7
    private const val TAG = "DOOM"

    private fun horizontal(v: Vector3): Vector3 {
      val h = Vector3(v.x, 0f, v.z)
      return if (h.length() < 1e-3f) Vector3(0f, 0f, -1f).also { Log.d(TAG, "mirada vertical") } else h.normalize()
    }
  }
}
