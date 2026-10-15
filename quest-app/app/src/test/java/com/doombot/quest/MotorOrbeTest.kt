package com.doombot.quest

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** La logica del orbe, sin escena: la misma que hud.html, ahora moviendo la burbuja 3D. */
class MotorOrbeTest {
  @Test
  fun el_matiz_base_es_el_cian_del_hud() {
    val (r, g, b, a) = MotorOrbe.hsl(193f, 1f, 0.5f, 1f).toList()
    assertTrue("rojo casi nulo: $r", r < 0.05f)
    assertTrue("azul pleno: $b", b > 0.95f)
    assertTrue("verde intermedio: $g", g in 0.6f..0.9f)
    assertEquals(1f, a, 0f)
  }

  @Test
  fun la_voz_sube_rapido_y_baja_despacio() {
    val m = MotorOrbe()
    m.paso(0.05f, EstadoOrbe.ESCUCHANDO, 1f)
    val trasSubir = m.amp
    assertTrue("ataque rapido: $trasSubir", trasSubir > 0.6f)
    m.paso(0.05f, EstadoOrbe.ESCUCHANDO, 0f)
    assertTrue("caida lenta: ${m.amp}", m.amp > 0.4f * trasSubir)
  }

  @Test
  fun un_error_se_transforma_en_medio_segundo_y_tiembla() {
    val m = MotorOrbe()
    m.paso(0.016f, EstadoOrbe.ERROR, 0f)
    assertTrue(m.sacudida > 0.9f)
    repeat(40) { m.paso(0.016f, EstadoOrbe.ERROR, 0f) }
    assertEquals(1f, m.m.caos, 1e-4f)
    assertEquals(170f, m.m.dh, 1e-3f)
    assertTrue("el temblor se apaga: ${m.sacudida}", m.sacudida < 0.1f)
  }
}
