# Resumen sesión sobremesa — 2026-09-01

Jornada larga en el sobremesa. Empezó como consolidación (juntar lo que estaba disperso en
ramas) y acabó desbloqueando la Capa 2 y construyendo la entrada de ficheros.

Todo está en `main` y **subido**: `origin/main` = `b031c8f`. No queda nada sin empujar.

---

## Parte 1 — Consolidación

### Las cinco ramas fusionadas

`main` iba 5 commits por detrás; *fast-forward* limpio. Después se fusionaron las cinco ramas
que quedaban fuera:

| Rama | Qué traía |
|---|---|
| `capa4-acciones` | Capa 2 (`wake.py`, `listener.py`), núcleo Rust, D-008 |
| `tarea/agente-acciones` | Capa de acciones vía Claude Code (D-014, D-017) |
| `tarea/obsidian` | Vault de Obsidian; contiene los commits de la anterior |
| `tarea/backend-claude` | Segundo backend: Claude por API |
| `tarea/contexto-claude-code` | `CLAUDE.md` |

Las seis ramas remotas **siguen existiendo en GitHub** aunque ya están contenidas en `main`.
Se pueden borrar cuando se quiera.

**Hallazgo de coordinación que conviene no repetir.** La sesión de Linux no sabía que
`capa4-acciones` existía: su nota afirma que la *wake word* «no existe en ningún branch», y
existía desde el 27/08. Dos líneas de trabajo avanzaron en paralelo sin verse. Es el mismo
fallo que D-012 registró para el registro de decisiones, ahora con ramas.

### Conflictos y dos falsas alarmas

Cinco conflictos, todos de ramas que **añaden** cosas distintas en el mismo punto. El único con
decisión real fue `chat.py`: se conserva `_generador(perfil, cfg)` de `backend-claude` en lugar
de la llamada directa a `OllamaGenerator`, porque ya elige entre los dos backends.

Dos cosas que parecían pérdidas y no lo eran —anotadas para no volver a investigarlas—:

- **Once tests «desaparecidos»** en `test_phrases.py` y `test_identity.py`: son renombrados de
  `capa4-acciones` (`test_reconoce_la_orden_con_muletillas` → `test_orden_con_muletillas`).
  Recuento idéntico: 38 y 10.
- **Líneas «perdidas»** en `chat.py`: las sustituye `backend-claude`, que es más reciente.

### La carpeta pasa a llamarse `doombot`

Era `jarvis-local`, herencia del nombre inicial. Ahora coinciden los tres nombres: repositorio,
paquete de Python y carpeta de trabajo.

**No se pudo renombrar: hubo que copiar.** Windows no deja renombrar una carpeta que es el
directorio de trabajo de un proceso vivo, y ese proceso era la propia sesión de Claude Code.
El Restart Manager no lo detecta porque no es un handle a un fichero, es el CWD. Se copió con
robocopy, se rehízo el `.venv` (guarda rutas absolutas en `pyvenv.cfg`, en los scripts de
activación, en el `.pth` del paquete editable y en cada `.exe` de `Scripts/`) y se movió la
carpeta de memoria de Claude Code, cuyo nombre deriva de la ruta.

---

## Parte 2 — Lo que se arregló y se construyó

### `keep_alive` (commit `652adc9`)

El perfil `workstation` mandaba `llm_keep_alive` como la cadena `"-1"`. Ollama la rechaza: no
es una duración válida. Medido: cadena → **400**, número → **200**. El sobremesa no podía
hablar con su propio modelo. La conversión vive en el backend, no en `profiles.py`, porque el
fichero de perfiles es dato medido y puede escribirlo de las dos formas.

### La Capa 2 deja de estar bloqueada (commit `5fe681a`, D-018)

CTranslate2 no empaqueta cuBLAS ni cuDNN. Instaladas por pip en un extra aparte, `voice-cuda`.
**Tres cosas que costaron averiguar porque el error confunde dos fallos distintos:**

1. `os.add_dll_directory()` **no basta**: CTranslate2 resuelve la DLL por una vía que no
   consulta esa lista. Hace falta tocar `PATH`.
2. Con el `PATH` puesto **seguía fallando** hasta instalar `nvidia-cuda-runtime-cu12`. cuBLAS
   se encontraba pero no cargaba. Era la segunda mitad del mensaje: *"or cannot be loaded"*.
3. `os.add_dll_directory()` devuelve un gestor de contexto que **retira el directorio al
   recolectarse**. Descartar el valor deja el registro sin efecto, con síntoma idéntico a no
   haberlo hecho.

**Medido aquí:** RTF **0,04** en caliente — 5,3 s de audio en 0,21 s. El portátil daba entre
0,28 y 0,59 con el mismo modelo. D-013 queda cerrado.

### Entrada de ficheros (commit `b031c8f`, D-019)

El objetivo es manejarlo sin manos, pero un fichero no se dicta. El gesto se parte en dos:
se suelta en el **buzón** (`%LOCALAPPDATA%\doombot\entrada`, fuera del repositorio) y después
se pide de palabra: *"lee lo último que te dejé"*, *"lee el archivo del contrato"*.

Resolución por conjuntos de palabras significativas. Se probaron las dos alternativas obvias y
ninguna sirve: la subcadena falla por el artículo (*"el contrato"* no está en
`contrato-alquiler-2026`) y el parecido global se hunde por la diferencia de longitud. Recorte
a 12.000 caracteres, media ventana de contexto: pasarse **no da error**, da una respuesta que
ignora medio fichero sin avisar. Probado de punta a punta contra Ollama real.

### Inventario de órdenes

Diez órdenes en lenguaje natural. **Seis hacen algo, cuatro son promesas vacías:**

| Orden | Estado |
|---|---|
| `remember`, `identify`, `recall`, `forget`, `progress` | funcionan |
| `read_file` | funciona (nuevo hoy) |
| `act` | código listo, falta el binario `claude` |
| `stop`, `silence`, `speak`, `repeat` | responden *"entendido, pero aún no puedo hacerlo"* |

Comandos de barra: `/ayuda` `/estado` `/memoria` `/borrar` `/entrada` `/obsidian` `/salir`

---

## Estado por capas

| Capa | Código | ¿Funciona? |
|---|---|---|
| 1 · Cerebro (LLM) | completo | **Sí** |
| 2 · Oídos (micro + wake word + Whisper) | completo | **Sí**, desde hoy. Sin probar con voz real |
| 3 · Memoria | completo | **Sí** |
| 4 · Acciones (Claude Code) | completo | **No**: falta el binario `claude` |
| 5 · Interfaz y voz (TTS) | **no existe** | Solo el prototipo HTML en `ui/prototipo` |
| Obsidian | completo | **Sí** |
| Ficheros | completo | **Sí**, desde hoy |

---

## Pendiente para la próxima sesión

### A. Decidido: se pospone

- **Pruebas de micrófono**, hasta nuevo aviso. Requieren que alguien hable.

### B. Necesita intervención manual

1. **Elegir micrófono.** Hay siete y el predeterminado del sistema es el virtual de Oculus, que
   no es un micro real. Se fija con `DOOMBOT_AUDIO_INPUT` en `.env` (un fragmento del nombre,
   no un índice). Candidatos vistos: unos auriculares, un A50, un CABLE de VB-Audio.
2. **`OLLAMA_MAX_LOADED_MODELS=1`** (D-010). El diagnóstico lo reclama en cada arranque. Es un
   `setx` más reiniciar Ollama.
3. **Instalar el CLI de `claude`** si se quiere la Capa 4 viva. No está en el equipo: solo hay
   un instalador de Claude Desktop en temporales, que no es lo mismo. Alternativa: dejarla
   dormida, el código falla con un mensaje claro.
4. **Borrar las seis ramas del remoto**, ya contenidas en `main`.

### C. Se puede hacer sin intervención

1. **Continuidad de conversación.** Cada pregunta va sin historial: no se puede decir *"y eso
   por qué"*. Es el hueco más grande para el uso por texto.
2. **`repeat`** está mal clasificada como orden de voz. *"¿qué has dicho?"* tiene sentido por
   escrito y es guardar la última respuesta en una variable.
3. **Módulo TTS con Kokoro**, midiendo latencia y VRAM aquí. Presupuesto medido: quedan ~5,9 GB
   libres con el LLM y Whisper cargados.
4. **`stop`, `silence`, `speak`** dejan de mentir en cuanto exista el TTS. Reconocer una orden y
   no hacer nada choca con el principio de `identity.py`.

### D. Ideas sin decidir

- **n8n.** Corre en el equipo Linux (`~/n8n`, puerto 5678), sin conectar a D.O.O.M. Falta
  decidir la dirección: ¿D.O.O.M dispara *workflows*, o n8n dispara acciones por *webhook*?
- **Enrutador velocidad/calidad** entre Ollama y Claude. Criterio de producto.
- **PDF y ofimática en el buzón.** Hoy solo entra texto, código y datos tabulares. Necesita una
  dependencia y es decisión aparte.
- **Arrastrar y soltar sobre el HUD** como segunda vía de entrada de ficheros, cuando el HUD
  esté cerrado.

### E. Capa 5, en su conversación aparte

Prototipo en `ui/prototipo/hud.html`: cinco estados, contrato `window.DOOM`, banco de pruebas
de voz. Pendiente cerrar el estilo artístico —el actual fija el comportamiento, no el aspecto—
y elegir motor de TTS midiendo en esta máquina.
