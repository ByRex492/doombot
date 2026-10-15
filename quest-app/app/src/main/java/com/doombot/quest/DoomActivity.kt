package com.doombot.quest

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.ComposeView
import com.doombot.quest.escena.Brazalete
import com.doombot.quest.escena.Circuitos
import com.doombot.quest.escena.Orbe3D
import com.doombot.quest.ui.Hud
import com.doombot.quest.ui.PanelAjustes
import com.doombot.quest.ui.PanelApps
import com.doombot.quest.ui.PanelBrazalete
import com.doombot.quest.ui.PanelChat
import com.doombot.quest.ui.PanelSistema
import com.doombot.quest.ui.PanelVoz
import com.meta.spatial.compose.ComposeFeature
import com.meta.spatial.compose.ComposeViewPanelRegistration
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector2
import com.meta.spatial.core.Vector3
import com.meta.spatial.isdk.IsdkFeature
import com.meta.spatial.isdk.IsdkGrabMovementType
import com.meta.spatial.isdk.IsdkGrabbable
import com.meta.spatial.isdk.IsdkPanelResize
import com.meta.spatial.isdk.ResizeMode
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.DpPerMeterDisplayOptions
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.toolkit.createPanelEntity
import com.meta.spatial.vr.LocomotionSystem
import com.meta.spatial.vr.VRFeature
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * D.O.O.M en realidad mixta: la burbuja 3D en el centro, las ventanas alrededor y el brazalete en
 * la muñeca, todo en tu habitacion.
 *
 * - **La burbuja** (escena/Orbe3D) es geometria 3D de verdad, no un panel: se coge con la mano y se
 *   estira con las dos. Debajo lleva sus subtitulos (un panel pequeño que la sigue).
 * - **Las ventanas** (Sistema, Registro, Aplicaciones, Ajustes) son paneles de Compose con
 *   ``IsdkPanelResize``: el sistema les añade la barra para agarrarlas y las esquinas para
 *   cambiarlas de tamaño, como las ventanas de Horizon OS. En modo ``Relayout`` el contenido se
 *   recoloca al nuevo tamaño en vez de estirarse.
 * - **Los circuitos** unen la burbuja con cada ventana abierta.
 * - **El brazalete** (escena/Brazalete) solo aparece al mirarte la palma.
 *
 * La escena se construye en codigo, sin Spatial Editor (D-041).
 */
class DoomActivity : AppSystemActivity(), Controlador.Escena {

  private val ambito = CoroutineScope(Dispatchers.Main)
  private val ctl by lazy { Controlador(this, this) }
  private val orbe by lazy { Orbe3D(this) }
  private val ventanas = LinkedHashMap<Int, Entity>()
  private var voz: Entity? = null
  private var brazalete: Entity? = null
  private var alConcederMicro: (() -> Unit)? = null

  /** Donde va cada cosa respecto a la cabeza: angulo (grados), distancia (m), altura relativa (m). */
  private data class Sitio(val angulo: Float, val distancia: Float, val altura: Float)

  private val sitioOrbe = Sitio(0f, 0.95f, -0.05f)
  private val sitios =
      mapOf(
          R.id.panel_sistema to Sitio(40f, 1.1f, -0.05f),
          R.id.panel_chat to Sitio(-40f, 1.1f, -0.05f),
          R.id.panel_apps to Sitio(0f, 1.05f, -0.55f),
          R.id.panel_ajustes to Sitio(0f, 0.85f, 0.02f),
      )

  /** Tamaño inicial de cada ventana (m) y limites al redimensionarla. */
  private data class Medidas(val ancho: Float, val alto: Float, val min: Vector2, val max: Vector2)

  private val medidas =
      mapOf(
          R.id.panel_sistema to Medidas(0.40f, 0.56f, Vector2(0.28f, 0.34f), Vector2(1.0f, 1.2f)),
          R.id.panel_chat to Medidas(0.50f, 0.58f, Vector2(0.32f, 0.30f), Vector2(1.6f, 1.4f)),
          R.id.panel_apps to Medidas(0.66f, 0.38f, Vector2(0.36f, 0.24f), Vector2(1.8f, 1.2f)),
          R.id.panel_ajustes to Medidas(0.62f, 0.76f, Vector2(0.40f, 0.40f), Vector2(1.4f, 1.6f)),
      )

  override fun registerFeatures(): List<SpatialFeature> =
      listOf(VRFeature(this), ComposeFeature(), IsdkFeature(this, spatial, systemManager))

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    systemManager.findSystem<LocomotionSystem>().enableLocomotion(false)
    scene.enablePassthrough(true)
    orbe.registrarMallas()
    val circuitos = Circuitos(this, { orbe.raiz }, { ventanas.values })
    circuitos.registrarMalla()
    systemManager.registerSystem(orbe.Sistema())
    systemManager.registerSystem(circuitos)
    systemManager.registerSystem(Brazalete { brazalete })
    systemManager.registerSystem(SeguirSistema())
    ctl.arrancar()
  }

  override fun onSceneReady() {
    super.onSceneReady()
    // La pose de la cabeza tarda unos instantes en ser real: se espera antes de colocar nada.
    ambito.launch {
      delay(900)
      orbe.crear(poseDelante(sitioOrbe))
      voz = Entity.createPanelEntity(R.id.panel_voz, Transform(poseDelante(sitioOrbe)))
      orbe.panelVoz = voz
      brazalete = Entity.createPanelEntity(R.id.panel_brazalete, Transform(), Visible(false))
      for (id in listOf(R.id.panel_sistema, R.id.panel_chat, R.id.panel_apps)) crear(id)
      if (Doom.conClave.isEmpty()) ctl.abrirAjustes() // primera vez: directo a configurar
    }
  }

  override fun registerPanels(): List<PanelRegistration> =
      listOf(
          panel(R.id.panel_voz, 0.40f, 0.17f) { PanelVoz(ctl) },
          panel(R.id.panel_brazalete, 0.22f, 0.11f) { PanelBrazalete(ctl) },
      ) + medidas.map { (id, m) ->
        panel(id, m.ancho, m.alto) {
          when (id) {
            R.id.panel_sistema -> PanelSistema(ctl)
            R.id.panel_chat -> PanelChat(ctl)
            R.id.panel_apps -> PanelApps(ctl)
            else -> PanelAjustes(ctl)
          }
        }
      }

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
    if (ventanas.containsKey(id)) return
    val m = medidas.getValue(id)
    ventanas[id] =
        Entity.createPanelEntity(
            id,
            Transform(poseDelante(sitios.getValue(id))),
            // Barra para agarrarla y esquinas para cambiar su tamaño, como en Horizon OS.
            IsdkPanelResize(enabled = true, resizeMode = ResizeMode.Relayout, minDimensions = m.min, maxDimensions = m.max),
            // Al moverla, gira para seguir mirandote.
            IsdkGrabbable(enabled = true, movementType = IsdkGrabMovementType.Billboard),
        )
  }

  private fun quitar(id: Int) {
    ventanas.remove(id)?.destroy()
  }

  override fun recolocar() {
    orbe.colocar(poseDelante(sitioOrbe))
    for ((id, e) in ventanas) e.setComponent(Transform(poseDelante(sitios.getValue(id))))
    Doom.anotar(TipoLinea.COMENTARIO, "Todo delante de usted, Mi Señor.")
  }

  override fun restablecerVentanas() {
    // Recrearlas es la forma segura de volver al tamaño de fabrica tras redimensionarlas.
    val abiertas = ventanas.keys.toList()
    abiertas.forEach { quitar(it) }
    abiertas.forEach { crear(it) }
    orbe.colocar(poseDelante(sitioOrbe))
    Doom.anotar(TipoLinea.COMENTARIO, "Ventanas como recien abiertas.")
  }

  override fun mostrarVentanas(visibles: Boolean) {
    for (e in ventanas.values) e.setComponent(Visible(visibles))
  }

  override fun mostrarAjustes(visible: Boolean) {
    if (visible) crear(R.id.panel_ajustes) else quitar(R.id.panel_ajustes)
  }

  override fun mostrarApps(visible: Boolean) {
    if (visible) crear(R.id.panel_apps) else quitar(R.id.panel_apps)
  }

  // -- permisos -----------------------------------------------------------------------------
  override fun pedirMicrofono(alConceder: () -> Unit) {
    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
      alConceder()
      return
    }
    alConcederMicro = alConceder
    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), PERMISO_MICRO)
  }

  @Deprecated("Deprecated in Java")
  override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
    super.onRequestPermissionsResult(requestCode, permissions, grantResults)
    if (requestCode != PERMISO_MICRO) return
    if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
      alConcederMicro?.invoke()
    } else {
      Doom.anotar(TipoLinea.AVISO, "Sin permiso de microfono: puede escribirme en el registro.")
    }
    alConcederMicro = null
  }

  override fun onDestroy() {
    ctl.cerrar()
    super.onDestroy()
  }

  /**
   * "Seguirme": la burbuja te acompaña con pereza. Solo se mueve cuando se ha quedado atras (como
   * un HUD que no tiembla con cada giro de cabeza), y se acerca poco a poco.
   */
  private inner class SeguirSistema : SystemBase() {
    override fun execute() {
      if (!Doom.orbeSigue) return
      val raiz = orbe.raiz ?: return
      val objetivo = poseDelante(sitioOrbe)
      val actual = raiz.getComponent<Transform>().transform
      if ((objetivo.t - actual.t).length() < 0.25f) return
      raiz.setComponent(Transform(Pose(actual.t + (objetivo.t - actual.t) * 0.06f, objetivo.q)))
    }
  }

  companion object {
    private const val PERMISO_MICRO = 7
    private const val TAG = "DOOM"

    private fun horizontal(v: Vector3): Vector3 {
      val h = Vector3(v.x, 0f, v.z)
      return if (h.length() < 1e-3f) Vector3(0f, 0f, -1f).also { Log.d(TAG, "mirada vertical") } else h.normalize()
    }
  }
}
