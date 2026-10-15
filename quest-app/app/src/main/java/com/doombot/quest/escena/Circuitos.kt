package com.doombot.quest.escena

import android.graphics.Color
import android.net.Uri
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.AlphaMode
import com.meta.spatial.runtime.DepthWrite
import com.meta.spatial.runtime.MaterialSidedness
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.runtime.SceneTexture
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.MeshCollision
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import kotlin.math.sin

/**
 * Los circuitos del HUD (D-036), en 3D: un hilo de luz de la burbuja a cada ventana abierta.
 *
 * Unen visualmente lo que en la ventana de escritorio unian las lineas entre el nucleo y los
 * paneles. Cada hilo es una barra fina de un metro, centrada, que se estira hasta la ventana y se
 * orienta hacia ella en cada fotograma: al mover la burbuja o una ventana, el hilo la sigue.
 */
class Circuitos(
    private val actividad: AppSystemActivity,
    private val orbe: () -> Entity?,
    private val ventanas: () -> Collection<Entity>,
) : SystemBase() {

  private val hilos = HashMap<Entity, Entity>()
  private var t = 0f
  private val material by lazy {
    SceneMaterial(SceneTexture(Color.valueOf(1f, 1f, 1f, 1f)), AlphaMode.TRANSLUCENT, SceneMaterial.UNLIT_SHADER).apply {
      setSidedness(MaterialSidedness.DOUBLE_SIDED)
      setDepthWrite(DepthWrite.DISABLE)
    }
  }

  fun registrarMalla() {
    // Centrada en el origen: da igual hacia que lado del eje mire la rotacion.
    actividad.registerMeshCreator("mesh://doom_hilo") { _: Entity ->
      SceneMesh.box(Vector3(-0.0011f, -0.0011f, -0.5f), Vector3(0.0011f, 0.0011f, 0.5f), material)
    }
  }

  override fun execute() {
    t += 0.016f
    material.setAlbedoColor(Color.valueOf(0.16f, 0.83f, 1f, 0.28f + 0.1f * sin(t * 2.2f)))
    val origen = orbe()?.getComponent<Transform>()?.transform?.t
    val actuales = ventanas().toSet()
    // Ventanas cerradas: fuera su hilo.
    hilos.keys.filter { it !in actuales }.forEach { hilos.remove(it)?.destroy() }
    if (origen == null) return
    for (v in actuales) {
      val hilo =
          hilos.getOrPut(v) {
            Entity.create(listOf(Mesh(Uri.parse("mesh://doom_hilo"), hittable = MeshCollision.NoCollision), Transform(), Scale(Vector3(1f))))
          }
      val destino = v.getComponent<Transform>().transform.t
      val dir = destino - origen
      val largo = dir.length()
      // Ventana escondida (desde el brazalete) o pegada a la burbuja: sin hilo.
      if (v.tryGetComponent<Visible>()?.isVisible == false || largo < 0.2f) {
        hilo.setComponent(Visible(false))
        continue
      }
      val d = dir * (1f / largo)
      // Sale del borde de la burbuja, no de su centro.
      val inicio = origen + d * 0.13f
      val medio = (inicio + destino) * 0.5f
      hilo.setComponents(
          listOf(
              Visible(true),
              Transform(Pose(medio, Quaternion.lookRotation(d, Vector3.Up))),
              Scale(Vector3(1f, 1f, largo - 0.13f))))
    }
  }
}
