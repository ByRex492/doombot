# Resumen sesión sobremesa — 2026-09-10

Sesión corta y de una sola pieza: **preparar el proyecto para que varias sesiones de Claude
trabajen en capas distintas a la vez**. No se construyó ninguna capa; se quitó lo que impedía
construir dos en paralelo.

Diez días después de la sesión del 01/09. Todo en `main` y subido: `origin/main` = `bd9cfb0`.

---

## Lo que se hizo

### 1. Registro de órdenes (D-020) — el cambio que lo habilita todo

`chat.py` tenía **siete bloques `if orden.command == ...` encadenados** en una función de 293
líneas. Funcionaba, pero era el punto por el que pasaba toda capa nueva: añadir una orden
significaba tocar esas veinte líneas.

Con una persona es una molestia. Con cinco ramas es un conflicto de fusión garantizado en cada
una, y **ninguno resoluble automáticamente**, porque git no sabe en qué orden van los bloques.

Ahora una capa escribe `su_paquete/orders.py` y decora sus manejadores:

```python
@orden("read_file")
def leer_fichero(s: Sesion, m: Match) -> None: ...
```

Las siete órdenes ya viven en su capa (`memory/`, `obsidian/`, `files/`, `actions/`). El punto
de colisión pasó a ser un punto de extensión.

Tres detalles que conviene no deshacer sin pensarlo:

- **Descubrimiento con `pkgutil`, no una lista escrita.** Una lista de módulos sería otro
  fichero común que toda capa tendría que editar: el mismo problema con otro nombre.
- **La `Sesion` sustituye a las variables del bucle.** `responder`, `con_contexto` y
  `preguntar` se **inyectan**, así que un manejador no depende de que la salida sea una
  consola. Cuando llegue la voz, cambia la `Sesion` y no los manejadores.
- **Dos tests para fallos propios del paralelo:** un manejador registrado para una orden que
  nadie puede pronunciar (código muerto silencioso), y dos capas disputándose la misma orden
  —que sin comprobarlo la ganaría la última importada, con un orden que depende de `pkgutil` y
  cambia de un equipo a otro—.

Verificado contra Ollama real: `remember`, `recall`, `forget`, `read_file` y `stop` se
comportan igual que antes.

### 2. Contrato del sintetizador, por adelantado

`backends/base.py` es fichero de integración y `capa/tts` no puede tocarlo, así que el
`Protocol` va **antes** que la implementación:

```python
class SpeechSynthesizer(Protocol):
    def say(self, texto: str) -> Audio: ...
    def stream(self, texto: str) -> Iterator[Audio]: ...
    @property
    def voice_name(self) -> str: ...
    @property
    def sample_rate(self) -> int: ...
```

- **Devuelve muestras, no un WAV.** Escribir a disco para releerlo añade latencia donde más se
  nota, e impide medir el nivel y cortar a media frase en el *barge-in*.
- **Reproducir no es cosa del sintetizador.** Eso es de la capa de voz. Separarlo es lo que
  hará posible interrumpir sin tocar el motor de síntesis.
- **`Audio.level()` une las dos ramas:** da la misma escala 0-1 que la amplitud del micrófono,
  así que **el HUD no tiene que saber cuál de los dos está sonando**.

### 3. Infraestructura del trabajo en paralelo

| Rama | Carpeta | Escribe en | Decisión reservada |
|---|---|---|---|
| `main` | `C:\Users\migue\doombot` | integración: fusiona y revisa | — |
| `capa/tts` | `C:\Users\migue\doombot-tts` | `src/doombot/tts/` | **D-021** |
| `capa/hud` | `C:\Users\migue\doombot-hud` | `ui/` | **D-022** |

Cada carpeta es un `git worktree` con su propio `.venv`. Las reglas están en `CLAUDE.md` —ahí y
no en una nota suelta, porque es el fichero que cada sesión lee sola al abrir el proyecto—.

**Los números de decisión se reservan de antemano.** Si no, dos ramas escriben D-021 a la vez y
el conflicto cae justo en `decisiones.md`, que es el fichero que más duele.

### 4. Limpieza del remoto

Borradas las cinco ramas ya fusionadas (`capa4-acciones` y las cuatro `tarea/*`), tras
comprobar una por una que no tenían **ni un commit** fuera de `main`. Quedan `main`,
`capa/tts` y `capa/hud`, las tres en `bd9cfb0`.

---

## Qué está haciendo cada sesión

**`capa/tts`** — el sintetizador con Kokoro. Tiene que medir en esta máquina la latencia hasta
el primer audio y el consumo (hay ~5,9 GB de VRAM libres con el LLM y Whisper cargados; Kokoro
en CPU es una alternativa a comparar), y juzgar la calidad de las voces **en español**, que
están entrenadas con menos material que las inglesas. Suyas son las órdenes `silence` y
`speak`, hoy sin implementar.

**`capa/hud`** — cerrar el estilo artístico e implementar el transporte por WebSocket. El
prototipo de `ui/prototipo/hud.html` fija el comportamiento, no el aspecto.

---

## Lo que integración espera recibir

Dos cosas ya previstas, que llegarán por sus notas de sesión porque tocan ficheros que ellas no
pueden editar:

1. **De `capa/tts`: el valor medido de `_ESCALA_NIVEL`.** Está en `backends/base.py` puesto a
   ojo (3,0) y marcado como provisional. Con un tono de prueba a 0,5 de amplitud ya satura,
   aunque la voz real tiene un valor eficaz bastante más bajo que un tono continuo.
2. **De `capa/tts`: las dependencias de Kokoro en `pyproject.toml`**, probablemente como un
   extra `voice-tts`, siguiendo lo que se hizo con `voice-cuda` en D-018.

---

## Pendiente, heredado del 01/09

Nada de esto cambió hoy.

### Necesita intervención manual

1. **Elegir micrófono** (`DOOMBOT_AUDIO_INPUT` en `.env`). Hay siete y el predeterminado del
   sistema es el virtual de Oculus, que no es un micro real.
2. **`OLLAMA_MAX_LOADED_MODELS=1`** (D-010). El diagnóstico lo reclama en cada arranque.
3. **Instalar el CLI de `claude`** si se quiere la Capa 4 viva. No está en el equipo.
4. **Pruebas de micrófono:** pospuestas por decisión del usuario, hasta nuevo aviso.

### Se puede hacer sin intervención

1. **Continuidad de conversación.** Cada pregunta va sin historial: no se puede decir *"y eso
   por qué"*. Es el hueco más grande para el uso por texto.
2. **`repeat`** está mal clasificada como orden de voz. Ahora es más fácil: `Sesion` ya guarda
   `ultima_respuesta`.
3. **PDF y ofimática en el buzón.** Hoy solo entra texto, código y datos tabulares (D-019).

### Sin decidir

**n8n** (corre en el equipo Linux, sin conectar), el **enrutador velocidad/calidad** entre
Ollama y Claude, y el **arrastrar y soltar sobre el HUD** como segunda vía de entrada de
ficheros.

---

## Estado por capas

| Capa | Código | ¿Funciona? |
|---|---|---|
| 1 · Cerebro (LLM) | completo | **Sí** |
| 2 · Oídos (micro + wake word + Whisper) | completo | **Sí**. Sin probar con voz real |
| 3 · Memoria | completo | **Sí** |
| 4 · Acciones (Claude Code) | completo | **No**: falta el binario `claude` |
| 5 · Voz (TTS) | **en `capa/tts`** | contrato listo, implementación en marcha |
| 5 · Interfaz (HUD) | **en `capa/hud`** | prototipo funcionando, estilo sin cerrar |
| Obsidian | completo | **Sí** |
| Ficheros | completo | **Sí** |
