"""El recorte del historial de conversacion (D-026).

Solo la funcion pura: probar el bucle entero de ``chat.py`` pediria un
Ollama real o un doble de cada pieza (memoria, agente, HUD...) para una
lógica que cabe en diez líneas y no depende de ninguna de ellas.
"""

from __future__ import annotations

from doombot.chat import _CARACTERES_POR_TOKEN, _FRACCION_HISTORIAL, _recortar_historial


def _turno(rol: str, chars: int) -> dict[str, str]:
    return {"role": rol, "content": "x" * chars}


def test_historial_vacio_devuelve_vacio():
    assert _recortar_historial([], num_ctx=8192) == []


def test_todo_cabe_si_hay_presupuesto_de_sobra():
    historial = [_turno("user", 10), _turno("assistant", 10)]
    assert _recortar_historial(historial, num_ctx=8192) == historial


def test_se_queda_con_los_turnos_mas_recientes():
    """Si no cabe todo, se corta por el principio, no por el final."""
    presupuesto = int(8192 * _FRACCION_HISTORIAL * _CARACTERES_POR_TOKEN)
    viejo = _turno("user", presupuesto)
    nuevo = _turno("user", 10)

    recortado = _recortar_historial([viejo, nuevo], num_ctx=8192)

    assert nuevo in recortado
    assert viejo not in recortado


def test_conserva_al_menos_un_turno_aunque_no_quepa_entero():
    """Un solo turno enorme no debe dejar el historial vacio del todo."""
    gigante = _turno("user", 10**6)
    assert _recortar_historial([gigante], num_ctx=2048) == [gigante]


def test_perfiles_con_menos_contexto_recortan_antes():
    historial = [_turno("user", 2000), _turno("assistant", 2000)]
    con_poco_contexto = _recortar_historial(historial, num_ctx=2048)
    con_mucho_contexto = _recortar_historial(historial, num_ctx=8192)
    assert len(con_poco_contexto) <= len(con_mucho_contexto)


def test_no_altera_el_orden_de_los_turnos_que_conserva():
    historial = [_turno("user", 10), _turno("assistant", 10), _turno("user", 10)]
    assert _recortar_historial(historial, num_ctx=8192) == historial
