package com.doombot.quest

import android.Manifest
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
import com.doombot.quest.ui.PanelChat
import com.doombot.quest.ui.PanelInfo
import com.doombot.quest.ui.PanelOrbe
import com.doombot.quest.ui.PanelSistema
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
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
 * y arrastrar) o el mando se coge y se deja donde se quiera, y los botones se pulsan igual. La
 * escena se construye en codigo, sin Spatial Editor: las entidades dependen de lo que se abre y se
 * cierra, y asi se compila tambien desde Linux (ver D-041).
 */
class DoomActivity : AppSystemActivity(), Controlador.Escena {

  private val ambito = CoroutineScope(Dispatchers.Main)
  private val ctl by lazy { Controlador(this, this) }
  private val entidades = HashMap<Int, Entity>()
  private var alConceder: ((Boolean) -> Unit)? = null
  private val huecosInfo = listOf(R.id.panel_info_0, R.id.panel_info_1, R.id.panel_info_2)

  /** Donde va cada panel respecto a la cabeza: angulo (grados), distancia (m), altura relativa (m). */
  private data class Sitio(val angulo: Float, val distancia: Float, val altura: Float)

  private val sitios =
      mapOf(
          R.id.panel_orbe to Sitio(0f, 1.0f, -0.12f),
          R.id.panel_sistema to Sitio(36f, 1.05f, -0.10f),
          R.id.panel_chat to Sitio(-36f, 1.05f, -0.10f),
          R.id.panel_apps to Sitio(0f, 0.95f, -0.66f),
          R.id.panel_ajustes to Sitio(0f, 0.78f, -0.06f),
          // Los de informacion aparecen delante, un poco escalonados, y se mueven con la mano.
          R.id.panel_info_0 to Sitio(18f, 0.85f, 0.18f),
          R.id.panel_info_1 to Sitio(-18f, 0.85f, 0.18f),
          R.id.panel_info_2 to Sitio(0f, 0.85f, 0.32f),
      )

  // Las manos (ISDK: pellizcar, coger, pulsar) las registra ya VRFeature desde el SDK 0.14: añadir
  // IsdkFeature a mano esta obsoleto y lo duplicaria.
  override fun registerFeatures(): List<SpatialFeature> = listOf(VRFeature(this), ComposeFeature())

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    systemManager.findSystem<LocomotionSystem>().enableLocomotion(false)
    scene.enablePassthrough(true)
    systemManager.registerSystem(SeguirSistema())
    ctl.arrancar()
  }

  override fun onSceneReady() {
    super.onSceneReady()
    // La pose de la cabeza tarda unos instantes en ser real: se espera antes de colocar nada.
    ambito.launch {
      delay(900)
      for (id in listOf(R.id.panel_orbe, R.id.panel_sistema, R.id.panel_chat, R.id.panel_apps)) crear(id)
      if (Doom.conClave.isEmpty()) ctl.abrirAjustes() // primera vez: directo a configurar
    }
  }

  override fun registerPanels(): List<PanelRegistration> =
      listOf(
          panel(R.id.panel_orbe, 0.42f, 0.58f) { PanelOrbe(ctl) },
          panel(R.id.panel_sistema, 0.40f, 0.56f) { PanelSistema(ctl) },
          panel(R.id.panel_chat, 0.48f, 0.56f) { PanelChat(ctl) },
          panel(R.id.panel_apps, 0.62f, 0.38f) { PanelApps(ctl) },
          panel(R.id.panel_ajustes, 0.60f, 0.74f) { PanelAjustes(ctl) },
      ) + huecosInfo.mapIndexed { n, id -> panel(id, 0.40f, 0.34f) { PanelInfo(ctl, n) } }

  private fun panel(id: Int, ancho: Float, alto: Float, contenido: @Composable () -> Unit) =
      ComposeViewPanelRegistration(
          id,
          composeViewCreator = { _, contexto ->
            ComposeView(contexto).apply {
              setContent { MaterialTheme(colorScheme = darkColorScheme(primary = Hud.c1)) { contenido() } }
            }
          },
          settingsCreator = {
            UIPanelSettings(
                shape = QuadShapeOptions(width = ancho, height = alto),
                style = PanelStyleOptions(themeResourceId = R.style.PanelTransparente),
                // 800 dp por metro: texto nitido y de tamaño comodo a un metro.
                display = DpPerMeterDisplayOptions(dpPerMeter = 800f),
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

  private fun crear(id: Int) {
    if (entidades.containsKey(id)) return
    val sitio = sitios.getValue(id)
    // PIVOT_Y: al moverlo sigue derecho y mirandote, que es lo que se espera de una pantalla.
    entidades[id] = Entity.createPanelEntity(id, Transform(poseDelante(sitio)), Grabbable(type = GrabbableType.PIVOT_Y))
  }

  private fun quitar(id: Int) {
    entidades.remove(id)?.destroy()
  }

  override fun recolocar() {
    for ((id, e) in entidades) e.setComponent(Transform(poseDelante(sitios.getValue(id))))
    Doom.anotar(TipoLinea.COMENTARIO, "Todo delante de usted, Mi Señor.")
  }

  override fun mostrarAjustes(visible: Boolean) {
    if (visible) crear(R.id.panel_ajustes) else quitar(R.id.panel_ajustes)
  }

  override fun mostrarApps(visible: Boolean) {
    if (visible) crear(R.id.panel_apps) else quitar(R.id.panel_apps)
  }

  override fun mostrarInfo(n: Int, visible: Boolean) {
    val id = huecosInfo.getOrNull(n) ?: return
    if (visible) {
      quitar(id) // si ya estaba, vuelve a aparecer delante con lo nuevo
      crear(id)
    } else {
      quitar(id)
    }
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
      val orbe = entidades[R.id.panel_orbe] ?: return
      val objetivo = poseDelante(sitios.getValue(R.id.panel_orbe))
      val actual = orbe.getComponent<Transform>().transform
      val distancia = (objetivo.t - actual.t).length()
      if (distancia < 0.25f) return
      val pos = actual.t + (objetivo.t - actual.t) * 0.06f
      orbe.setComponent(Transform(Pose(pos, objetivo.q)))
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
