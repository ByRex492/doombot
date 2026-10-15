package com.doombot.quest.escena

import com.doombot.quest.Doom
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Query
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.AvatarBody
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible

/**
 * El brazalete: un menu pegado a la muñeca, que solo aparece cuando lo miras.
 *
 * La version anterior era una ventana mas, siempre a la vista y sin relacion con la mano. Esta
 * sigue a la mano en cada fotograma (``AvatarBody``) y se enseña solo si a la vez miras hacia la
 * mano y la palma te mira, como el menu de muñeca de Meta (la logica es la de su ejemplo
 * WristAttachedSystem, del Spatial Scanner). Con histeresis: aparece con criterio estricto y se
 * va con uno mas laxo, para que no parpadee en el borde.
 *
 * Se ajusta en Ajustes: encendido o apagado, en que mano, y su tamaño.
 */
class Brazalete(private val panel: () -> Entity?) : SystemBase() {

  private var visible = false

  override fun execute() {
    val e = panel() ?: return
    val cfg = Doom.config
    if (!cfg.brazalete) {
      ponerVisible(e, false)
      return
    }
    val cuerpo = cuerpo() ?: return
    val izquierda = cfg.manoBrazalete != "derecha"
    val mano = if (izquierda) cuerpo.leftHand else cuerpo.rightHand
    if (!cuerpo.head.hasComponent<Transform>() || !mano.hasComponent<Transform>()) {
      ponerVisible(e, false) // mano fuera de la vista o mando desconectado
      return
    }
    val cabeza = cuerpo.head.getComponent<Transform>().transform
    val muneca = mano.getComponent<Transform>().transform

    // Desplazamiento sobre la muñeca, el del ejemplo de Meta para la mano izquierda; en la derecha,
    // en espejo.
    val signo = if (izquierda) 1f else -1f
    val giro =
        Quaternion.fromAxisAngle(Vector3.Right, -30f)
            .times(Quaternion.fromAxisAngle(Vector3.Up, -55f * signo))
            .times(Quaternion.fromAxisAngle(Vector3.Forward, -90f * signo))
            .normalize()
    val rot = muneca.q.times(giro)
    val pos = muneca.t + rot.times(Vector3(0.08f * signo, -0.04f, -0.02f))
    e.setComponents(listOf(Transform(Pose(pos, cabeza.q)), Scale(Vector3(cfg.tamanoBrazalete))))

    val haciaMano = (pos - cabeza.t).normalize()
    val mirando = cabeza.forward().dot(haciaMano)
    val palma = rot.times(Vector3.Forward).dot(haciaMano)
    val ver = if (visible) mirando > 0.75f && palma > 0.25f else mirando > 0.85f && palma > 0.4f
    ponerVisible(e, ver)
  }

  private fun ponerVisible(e: Entity, ver: Boolean) {
    if (ver == visible) return
    visible = ver
    e.setComponent(Visible(ver))
  }

  private fun cuerpo(): AvatarBody? =
      Query.where { has(AvatarBody.id) }
          .eval()
          .firstOrNull { it.isLocal() && it.getComponent<AvatarBody>().isPlayerControlled }
          ?.getComponent<AvatarBody>()
}
