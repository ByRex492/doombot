package com.doombot.quest.escena

import android.graphics.Color
import android.net.Uri
import com.doombot.quest.Doom
import com.doombot.quest.MotorOrbe
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector2
import com.meta.spatial.core.Vector3
import com.meta.spatial.isdk.IsdkGrabConstraints
import com.meta.spatial.runtime.AlphaMode
import com.meta.spatial.runtime.DepthWrite
import com.meta.spatial.runtime.MaterialSidedness
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.runtime.SceneTexture
import com.meta.spatial.runtime.TriangleMesh
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.MeshCollision
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.Transform
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin
import kotlin.random.Random

/**
 * La burbuja de D.O.O.M en 3D: el mismo orbe del HUD (ui/prototipo/hud.html), pero con volumen.
 *
 * - Una **raiz** invisible con un colisionador de esfera: es lo que se coge. Con una mano se mueve;
 *   con las dos, se estira o se encoge (``IsdkGrabConstraints`` con dos agarradores).
 * - Las **piezas** que se ven: nucleo, resplandor y halo (esferas translucidas), el disco de 72
 *   marcas que reacciona a la voz, tres arcos orbitales inclinados y un aro fino. Cada pieza tiene
 *   su material, que se recolorea en cada fotograma con los parametros del estado (MotorOrbe).
 *
 * Las piezas no cuelgan de la raiz: en cada fotograma se colocan desde ella. Asi el disco de
 * marcas puede mirar siempre al usuario mientras los arcos giran en sus propios planos, sin
 * depender de como se combinan las rotaciones padre-hijo.
 *
 * Sin shaders propios a proposito: piden el NDK y Meta los marca como experimentales. Geometria
 * propia, materiales sin luz y translucidos, y movimiento dan el efecto holografico.
 */
class Orbe3D(private val actividad: AppSystemActivity) {

  private val motor = MotorOrbe()
  private val materiales = HashMap<String, SceneMaterial>()
  private val piezas = HashMap<String, Entity>()
  var raiz: Entity? = null
    private set
  /** La que va debajo: estado y subtitulos. La coloca este sistema siguiendo a la burbuja. */
  var panelVoz: Entity? = null

  // -- mallas --------------------------------------------------------------------------------
  private fun material(nombre: String, escribeProfundidad: Boolean = false): SceneMaterial =
      materiales.getOrPut(nombre) {
        SceneMaterial(SceneTexture(Color.valueOf(1f, 1f, 1f, 1f)), AlphaMode.TRANSLUCENT, SceneMaterial.UNLIT_SHADER).apply {
          setSidedness(MaterialSidedness.DOUBLE_SIDED)
          if (!escribeProfundidad) setDepthWrite(DepthWrite.DISABLE)
        }
      }

  fun registrarMallas() {
    actividad.registerMeshCreator("mesh://doom_nucleo") { _: Entity -> SceneMesh.sphere(0.032f, material("nucleo", true)) }
    actividad.registerMeshCreator("mesh://doom_brillo") { _: Entity -> SceneMesh.sphere(0.056f, material("brillo")) }
    actividad.registerMeshCreator("mesh://doom_halo") { _: Entity -> SceneMesh.sphere(0.11f, material("halo")) }
    actividad.registerMeshCreator("mesh://doom_marcas") { _: Entity -> SceneMesh.fromTriangleMesh(marcas(material("marcas")), false) }
    actividad.registerMeshCreator("mesh://doom_aro") { _: Entity -> SceneMesh.fromTriangleMesh(tubo(0.072f, 0.0012f, 0f, 360f, material("aro")), false) }
    for (i in 0 until 3) {
      actividad.registerMeshCreator("mesh://doom_arco$i") { _: Entity ->
        SceneMesh.fromTriangleMesh(arcos(0.112f + i * 0.02f, 0.0022f, material("arco$i")), false)
      }
    }
  }

  /** Un tramo de toro: tubo de radio ``r`` alrededor de un circulo de radio ``radio``, en el plano XY. */
  private fun tubo(radio: Float, r: Float, desde: Float, largo: Float, mat: SceneMaterial, segU: Int = 96, segV: Int = 6): TriangleMesh =
      malla(listOf(Triple(desde, largo, segU)), radio, r, segV, mat)

  /** Dos arcos opuestos en un mismo anillo, como los arcos orbitales del HUD. */
  private fun arcos(radio: Float, r: Float, mat: SceneMaterial): TriangleMesh =
      malla(listOf(Triple(0f, 110f, 48), Triple(180f, 66f, 30)), radio, r, 6, mat)

  private fun malla(tramos: List<Triple<Float, Float, Int>>, radio: Float, r: Float, segV: Int, mat: SceneMaterial): TriangleMesh {
    val nv = tramos.sumOf { (it.third + 1) * (segV + 1) }
    val ni = tramos.sumOf { it.third * segV * 6 }
    val tm = TriangleMesh(nv, ni, intArrayOf(0, ni), arrayOf(mat))
    val pos = FloatArray(nv * 3)
    val nor = FloatArray(nv * 3)
    val uvs = FloatArray(nv * 2)
    val col = IntArray(nv) { Color.WHITE }
    val idx = IntArray(ni)
    var v = 0
    var k = 0
    for ((desde, largo, segU) in tramos) {
      val base = v
      for (i in 0..segU) {
        val a = Math.toRadians((desde + largo * i / segU).toDouble())
        val cx = cos(a).toFloat()
        val cy = sin(a).toFloat()
        for (j in 0..segV) {
          val b = 2 * PI * j / segV
          val nx = cos(b).toFloat() * cx
          val ny = cos(b).toFloat() * cy
          val nz = sin(b).toFloat()
          pos[v * 3] = cx * radio + nx * r
          pos[v * 3 + 1] = cy * radio + ny * r
          pos[v * 3 + 2] = nz * r
          nor[v * 3] = nx
          nor[v * 3 + 1] = ny
          nor[v * 3 + 2] = nz
          uvs[v * 2] = i.toFloat() / segU
          uvs[v * 2 + 1] = j.toFloat() / segV
          v++
        }
      }
      for (i in 0 until segU) for (j in 0 until segV) {
        val a0 = base + i * (segV + 1) + j
        val a1 = a0 + segV + 1
        idx[k++] = a0; idx[k++] = a1; idx[k++] = a0 + 1
        idx[k++] = a0 + 1; idx[k++] = a1; idx[k++] = a1 + 1
      }
    }
    tm.updateGeometry(0, pos, nor, uvs, col)
    tm.updatePrimitives(0, idx)
    return tm
  }

  /** El disco de 72 marcas radiales del HUD: una de cada seis, mas larga y mas brillante. */
  private fun marcas(mat: SceneMaterial): TriangleMesh {
    val n = 72
    val tm = TriangleMesh(n * 4, n * 6, intArrayOf(0, n * 6), arrayOf(mat))
    val pos = FloatArray(n * 12)
    val nor = FloatArray(n * 12)
    val uvs = FloatArray(n * 8)
    val col = IntArray(n * 4)
    val idx = IntArray(n * 6)
    for (i in 0 until n) {
      val larga = i % 6 == 0
      val a = 2 * PI * i / n
      val dx = cos(a).toFloat()
      val dy = sin(a).toFloat()
      val r1 = 0.082f
      val r2 = r1 + if (larga) 0.014f else 0.0065f
      val w = if (larga) 0.0018f else 0.0011f
      val px = -dy * w
      val py = dx * w
      val esquinas = listOf(dx * r1 - px to dy * r1 - py, dx * r1 + px to dy * r1 + py, dx * r2 + px to dy * r2 + py, dx * r2 - px to dy * r2 - py)
      esquinas.forEachIndexed { c, (x, y) ->
        val v = i * 4 + c
        pos[v * 3] = x; pos[v * 3 + 1] = y; pos[v * 3 + 2] = 0f
        nor[v * 3 + 2] = 1f
        uvs[v * 2] = if (c == 1 || c == 2) 1f else 0f
        uvs[v * 2 + 1] = if (c >= 2) 1f else 0f
        col[v] = if (larga) Color.WHITE else Color.rgb(170, 170, 170)
      }
      val b = i * 4
      intArrayOf(b, b + 1, b + 2, b, b + 2, b + 3).copyInto(idx, i * 6)
    }
    tm.updateGeometry(0, pos, nor, uvs, col)
    tm.updatePrimitives(0, idx)
    return tm
  }

  // -- entidades ------------------------------------------------------------------------------
  fun crear(pose: Pose): Entity {
    raiz?.let { return it }
    val r =
        Entity.create(
            listOf(
                Transform(pose),
                Scale(Vector3(1f)),
                // Lo que se coge: una esfera algo mayor que lo que se ve, para acertar facil.
                Sphere(0.15f),
                Grabbable(type = GrabbableType.PIVOT_Y),
                // Con las dos manos, estirar o encoger la burbuja.
                IsdkGrabConstraints(maxGrabbers = 2, scaleMinMax = Vector2(0.4f, 3.0f)),
            ))
    raiz = r
    for (nombre in listOf("halo", "brillo", "nucleo", "marcas", "aro", "arco0", "arco1", "arco2")) {
      piezas[nombre] =
          Entity.create(
              listOf(
                  Mesh(Uri.parse("mesh://doom_$nombre"), hittable = MeshCollision.NoCollision),
                  Transform(pose),
                  Scale(Vector3(1f)),
              ))
    }
    return r
  }

  fun colocar(pose: Pose) {
    raiz?.setComponent(Transform(pose))
  }

  /** Mueve y recolorea las piezas. Lo llama el sistema en cada fotograma. */
  fun actualizar(dt: Float, cabeza: Pose) {
    val r = raiz ?: return
    motor.paso(dt, Doom.orbe, Doom.amplitud)
    val m = motor.m
    val centro = r.getComponent<Transform>().transform.t
    val s = r.tryGetComponent<Scale>()?.scale?.x ?: 1f

    // Mirando al usuario, solo en horizontal: el disco se ve siempre de frente.
    val haciaUsuario = Vector3(centro.x - cabeza.t.x, 0f, centro.z - cabeza.t.z)
    val base = if (haciaUsuario.length() < 1e-3f) Quaternion() else Quaternion.lookRotationAroundY(haciaUsuario.normalize())

    val temblor = motor.sacudida * 0.012f
    val c =
        if (temblor > 0f) centro + Vector3((Random.nextFloat() - .5f) * temblor, (Random.nextFloat() - .5f) * temblor, 0f)
        else centro
    val respira = 1 + sin(motor.t * 2 * PI.toFloat() * m.bpm) * m.breath
    val voz = 1 + motor.amp * m.react * 0.16f
    val tam = s * (m.r / 0.33f)

    fun poner(nombre: String, rot: Quaternion, escala: Float, dl: Float, alfa: Float) {
      val e = piezas[nombre] ?: return
      e.setComponents(listOf(Transform(Pose(c, rot)), Scale(Vector3(escala))))
      val rgba = motor.color(dl, alfa)
      materiales[nombre]?.setAlbedoColor(Color.valueOf(rgba[0], rgba[1], rgba[2], rgba[3]))
    }

    poner("halo", base, tam * respira * (1 + motor.amp * m.react * 0.3f), 0f, 0.16f * m.glow)
    poner("brillo", base, tam * respira * voz, 0f, 0.5f * m.glow + 0.12f)
    poner("nucleo", base, tam * respira, 32f, 0.95f * max(0.45f, m.glow))
    poner("marcas", base.times(Quaternion.fromAxisAngle(Vector3.Forward, motor.ang)), tam * voz, 14f, 0.4f + 0.5f * m.glow)
    poner("aro", base, tam * respira, 20f, 0.25f + 0.25f * m.glow)
    for (i in 0 until 3) {
      // Cada arco en su plano inclinado; al pensar (orbit alto) son los protagonistas.
      val inclinacion = Quaternion.fromAxisAngle(Vector3.Right, 62f + i * 24f).times(Quaternion.fromAxisAngle(Vector3.Up, i * 55f))
      val giro = Quaternion.fromAxisAngle(Vector3.Forward, -motor.ang * (1.4f + i * 0.5f) + i * 120f)
      poner("arco$i", base.times(inclinacion).times(giro), tam, 10f, m.orbit * (0.9f - i * 0.2f) + 0.04f)
    }

    // Los subtitulos, justo debajo de la burbuja y mirando al usuario.
    // Algo mas abajo que la esfera que se coge, para que sus botones no queden dentro de ella.
    panelVoz?.setComponent(Transform(Pose(centro - Vector3(0f, 0.23f * s, 0f), base)))
  }

  /** El sistema que la anima: un paso por fotograma con el tiempo real transcurrido. */
  inner class Sistema : SystemBase() {
    private var antes = 0L

    override fun execute() {
      val ahora = System.nanoTime()
      val dt = if (antes == 0L) 0.016f else ((ahora - antes) / 1e9f).coerceIn(0f, 0.05f)
      antes = ahora
      actualizar(dt, getScene().getViewerPose())
    }
  }
}
