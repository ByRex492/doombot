# Resumen sesión Linux — 2026-10-14

Desde el portátil Linux (perfil `cpu_only`), con Claude Code. Rama **`tarea/refinar-respuestas`**,
sacada de `main` (ad432fe, que ya tiene todo `tarea/agente-local`). Sin fusionar: fusionar desde el
sobremesa.

## Refinar las respuestas (D-039)

Pedido: modelos gratuitos útiles para refinar las respuestas. Tras investigar las capas gratuitas
de hoy (resultado completo en D-039), se hicieron dos cosas:

- **Repaso final** (`agent/refinado.py`): al terminar, otro modelo de la cadena revisa la
  respuesta contra lo consultado y la corrige si hace falta. `DOOMBOT_AGENT_REFINAR=auto|siempre|no`.
  La ventana enseña "repasando la respuesta…" y, en SISTEMA, "Repaso de respuestas".
- **`leer_url`** (en `agent/web.py`): lee páginas con Jina Reader, sin abrir Chromium. Es ahora lo
  primero para leer fuentes; está en el prompt y en las cuatro skills.
  `DOOMBOT_JINA_API_KEY` es opcional.
- **Arreglo de paso**: en un modo, la segunda opinión podía darla el mismo modelo que proponía la
  acción. Ahora mira la cadena del modo.
- `tests/test_ventana.py` esperaba 19 herramientas desde que se añadió `buscar_web`, y ya fallaba
  en `main`. Ahora espera 21, con `leer_url`.

Integración tocada (revisar al fusionar): `config.py` (`agent_refinar`), `.env.example`,
`ventana/puente.py` (`repaso` en `iniciar`), `ui/ventana/doom.html`.

**Verificado en real** con las claves de este portátil:
- el repaso corrigió un borrador con dos cifras mal y dejó intacto uno correcto;
- una orden completa de investigación usó `buscar_web` y `leer_url`, sin navegador, citó la fuente
  y la repasó otro modelo.

Suite sin hardware en verde.

## Otro equipo (amarinosa)

`python -m doombot ventana` daba "No hay respuesta de Ollama": ese equipo tenía el código antiguo,
donde `ventana` no existe y se toma como pregunta. Hay que hacer `git pull` de `main` allí e
instalar los extras (`hud`, `agent-web`), el GTK del sistema y los enlaces de `gi` y `cairo` (README).

## Qué hacer en el sobremesa

1. Fusionar `tarea/refinar-respuestas` y pasar `pytest -m "not hardware"`.
2. Probar una investigación con `ollama:gemma4:12b` en la cadena: ver si el repaso lo hace un
   modelo en la nube o el local, y cuánto tarda.
3. Si se quiere, la clave gratuita de NVIDIA: un modelo de otra familia (Nemotron) hace que el
   repaso, el contraste y la segunda opinión discrepen de verdad.

## Ideas que quedan

- **Prompt Guard de Groq** (`llama-prompt-guard-2-86m`, gratis en la cuenta): avisar cuando una
  página leída intenta darle órdenes al agente. Lee 512 tokens de cada vez.
- **Ordenar fragmentos por significado** con el modelo de embeddings que ya tiene el proyecto, en
  vez de buscar la palabra exacta (`fastembed`, extra `voice`).
