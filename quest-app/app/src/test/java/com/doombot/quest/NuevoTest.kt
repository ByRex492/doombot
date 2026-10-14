package com.doombot.quest

import com.doombot.quest.datos.Aspecto
import com.doombot.quest.datos.Perfil
import com.doombot.quest.ia.FiltroPensamiento
import com.doombot.quest.sistema.N8n
import com.doombot.quest.sistema.Web
import com.doombot.quest.util.Calculadora
import com.doombot.quest.voz.Frases
import com.doombot.quest.voz.Reflejos
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Lo nuevo del 15/10/2026: aspecto, calculadora, web, frases, memoria, n8n y confirmacion. */
class NuevoTest {
  private val noche = Perfil("perfil-abc123", "Noche", "#FF00AA", "#112233")

  // -- aspecto (las mismas reglas que ventana/preferencias.py) -----------------------------------
  @Test
  fun un_perfil_activo_pinta_sus_colores() {
    val a = Aspecto.limpiar(Aspecto(tema = noche.id, c1 = "#000000", perfiles = listOf(noche)))
    assertEquals("#ff00aa", a.c1)
    assertEquals("#112233", a.c2)
    assertEquals(noche.id, a.tema)
  }

  @Test
  fun lo_raro_vuelve_al_defecto() {
    val a = Aspecto.limpiar(Aspecto(tema = "inventado", c1 = "red;}", luz = 9f, velocidad = Float.NaN))
    assertEquals("jarvis", a.tema)
    assertEquals("#29d3ff", a.c1)
    assertEquals(1.6f, a.luz)
    assertEquals(1f, a.velocidad)
  }

  @Test
  fun un_perfil_roto_se_descarta_entero_y_no_hay_ids_repetidos() {
    val rotos = listOf(noche.copy(id = "otro"), noche.copy(id = "perfil-x", c1 = "red"), noche.copy(id = "perfil-y", nombre = " \n "), noche, noche)
    assertEquals(listOf("perfil-abc123"), Aspecto.perfilesLimpios(rotos).map { it.id })
  }

  @Test
  fun crear_editar_renombrar_y_borrar_perfiles() {
    var a = Aspecto().conColor(principal = true, "#123456")
    assertEquals("propio", a.tema)
    a = a.crearPerfil("Noche", id = "perfil-1")
    assertEquals("perfil-1", a.tema)
    a = a.conColor(principal = false, "#abcdef")
    assertEquals("#abcdef", a.perfilActivo!!.c2) // con un perfil activo, el color va al perfil
    a = a.crearPerfil("Noche", id = "perfil-2")
    assertEquals("Noche 2", a.perfilActivo!!.nombre)
    a = a.renombrar("perfil-2", "  Día\n claro ")
    assertEquals("Día claro", a.perfilActivo!!.nombre)
    a = a.borrarPerfil("perfil-2")
    assertEquals("propio", a.tema)
    assertEquals(1, a.restablecido().perfiles.size) // restablecer no se lleva los perfiles
  }

  // -- calcular ---------------------------------------------------------------------------------
  @Test
  fun calcula_con_precedencia_funciones_y_sin_colas() {
    assertEquals("216", Calculadora.formatear(Calculadora.evaluar("0.5*3*12^2")))
    assertEquals("512", Calculadora.formatear(Calculadora.evaluar("2^3^2")))
    assertEquals("0.3", Calculadora.formatear(Calculadora.evaluar("0,1 + 0,2")))
    assertEquals("4.442882938", Calculadora.formatear(Calculadora.evaluar("sqrt(2)*pi")))
    assertEquals("-7", Calculadora.formatear(Calculadora.evaluar("-(3+4)")))
  }

  @Test(expected = Calculadora.ErrorDeFormula::class)
  fun una_formula_no_es_codigo() {
    Calculadora.evaluar("system(1)")
  }

  // -- web ---------------------------------------------------------------------------------------
  @Test
  fun resultados_de_duckduckgo_sin_redireccion_ni_anuncios() {
    val html =
        """
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fes.wikipedia.org%2Fwiki%2FMadrid&rut=x">Madrid - <b>Wikipedia</b></a>
        <a class="result__snippet" href="#">Capital de <b>España</b> &amp; mas</a>
        <a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Anuncio</a>
        <a class="result__snippet" href="#">compra</a>
        """.trimIndent()
    val r = Web.resultados(html)
    assertEquals(1, r.size)
    assertEquals("https://es.wikipedia.org/wiki/Madrid", r[0].url)
    assertEquals("Madrid - Wikipedia", r[0].titulo)
    assertEquals("Capital de España & mas", r[0].resumen)
  }

  @Test
  fun lectura_de_jina_sin_cabecera_y_fragmentos_sin_tildes() {
    val (titulo, texto) = Web.limpiarLectura("Title: Madrid\nURL Source: https://x\n\nMarkdown Content:\nMadrid es la capital.")
    assertEquals("Madrid", titulo)
    assertEquals("Madrid es la capital.", texto)
    assertEquals(1, Web.fragmentos("La poblacion de Madrid es grande.", "población").size)
  }

  @Test
  fun lo_local_no_sale_hacia_el_lector() {
    assertTrue(Web.esLocal("http://192.168.1.10:5678/x"))
    assertTrue(Web.esLocal("http://localhost/"))
    assertFalse(Web.esLocal("https://es.wikipedia.org/wiki/Madrid"))
    assertEquals("", Web.normalizar("recetas de paella"))
  }

  // -- voz por frases y pensamiento oculto ---------------------------------------------------------
  @Test
  fun frases_completas_segun_llegan_y_las_cortas_se_juntan() {
    val f = Frases(minimo = 10)
    assertEquals(emptyList<String>(), f.anadir("Sí. Claro"))
    assertEquals(listOf("Sí. Claro que puedo, Sr. García."), f.anadir(" que puedo, Sr. García. Ahora"))
    assertEquals("Ahora", f.resto())
  }

  @Test
  fun lo_que_piensa_el_modelo_no_se_dice_aunque_llegue_partido() {
    val f = FiltroPensamiento()
    val dicho = listOf("Hola <thi", "nk>esto no</th", "ink> mundo").joinToString("") { f.pasar(it) }
    assertEquals("Hola  mundo", dicho)
  }

  // -- memoria, confirmacion y n8n -----------------------------------------------------------------
  @Test
  fun recuerda_que_guarda_las_palabras_originales() {
    assertEquals("me gusta el café solo", Reflejos.recordatorio("Doom, recuerda que me gusta el café solo."))
    assertNull(Reflejos.recordatorio("¿qué tiempo hace?"))
    assertEquals(Reflejos.Orden.OLVIDAR_HECHO, Reflejos.reconocer("Olvida eso"))
  }

  @Test
  fun solo_un_si_claro_confirma() {
    assertTrue(Reflejos.esAfirmacion("Sí, adelante"))
    assertFalse(Reflejos.esAfirmacion("no"))
    assertFalse(Reflejos.esAfirmacion("espera un momento"))
  }

  @Test
  fun n8n_solo_lo_de_la_lista_blanca_comparando_sin_tildes() {
    val flujos = mapOf("Riego del jardín" to "webhook/riego")
    assertEquals("webhook/riego", N8n.ruta("riego del jardin", flujos))
    assertNull(N8n.ruta("borrar todo", flujos))
  }
}
