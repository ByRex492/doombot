# Estructura del proyecto

Organizado por responsabilidad, no por tecnología. Un módulo se llama como el
problema que resuelve, no como la librería que usa por dentro: así cambiar de
librería no obliga a renombrar nada.

```
doombot/
├── profiles.toml        Perfiles de hardware medidos (datos, no código)
├── pyproject.toml       Dependencias, Python 3.12 fijado, ruff, pytest
├── .env.example         Plantilla de la configuración local
├── .gitattributes       Normaliza finales de línea entre equipos
├── docs/
├── src/doombot/
│   ├── paths.py         Todas las rutas, derivadas en ejecución
│   ├── config.py        Lo que cambia de un equipo a otro
│   ├── profiles.py      Detección de hardware y elección de perfil
│   ├── identity.py      Qué dice saber hacer, según lo que hay instalado
│   ├── chat.py          Modo interactivo: junta todas las capas en un bucle
│   ├── hud_server.py    Transporte del HUD por WebSocket (D-022)
│   ├── backends/        Contratos e implementaciones intercambiables
│   │   ├── openai_compat.py  Cualquier API tipo OpenAI: Groq, Gemini, NVIDIA... (D-034)
│   │   ├── proveedores.py    Catálogo: de "groq:modelo" a un generador
│   │   └── varios.py    Cadena (si uno falla, otro) y Consejo (contrastar)
│   ├── memory/          Qué recuerda D.O.O.M (+ orders.py)
│   ├── phrases/         Frases textuales y órdenes: qué se puede decir
│   ├── orders/          Registro: qué capa atiende cada orden
│   │   └── registry.py  La Sesión, el decorador y el despachador
│   ├── voice/           Audio de entrada, palabra de activación y salida hablada
│   │   ├── capture.py   Micrófono: graba a WAV, detecta silencio, mide nivel
│   │   ├── wake.py      Palabra de activación y push-to-talk
│   │   ├── listener.py  Bucle de escucha: la máquina de estados
│   │   ├── speaker.py   Texto del modelo -> frases -> Kokoro -> Player, en paralelo
│   │   ├── player.py    Cola de audio interrumpible, mide nivel para el HUD
│   │   └── orders.py    `stop` y `repeat`
│   ├── tts/             Síntesis de voz (+ orders.py)
│   │   ├── synth.py     Kokoro por ONNX Runtime, con troceo por frase
│   │   ├── dsp.py       Procesado sutil: corte de graves y sala pequeña
│   │   └── download.py  Trae los ficheros del modelo la primera vez
│   ├── actions/         Capa de acciones: tareas reales, no solo respuestas
│   │   ├── claude_code.py  Delega en `claude -p`, headless
│   │   ├── n8n.py       Dispara workflows por webhook, lista blanca (D-030)
│   │   └── orders.py    `act` y `flow`
│   ├── agent/           Agente local: cumple órdenes solo, con herramientas (D-033)
│   │   ├── bucle.py     Pensar, actuar, observar: confirmación, límites, enmascarado
│   │   ├── herramientas.py  Qué es una herramienta: función + narración + riesgo
│   │   ├── sistema.py   Ficheros y comandos; qué es "solo lectura" y qué es sensible
│   │   ├── apps.py      Reconoce, abre y cierra las aplicaciones instaladas
│   │   ├── web.py       Navegador propio (Playwright) y el navegador del usuario
│   │   ├── montaje.py   Elige el cerebro, junta las herramientas, escribe el prompt
│   │   ├── revision.py  Segunda opinión de otro modelo antes de lo irreversible
│   │   ├── consola.py   `python -m doombot agente`
│   │   └── orders.py    `agent`, desde el chat
│   ├── ventana/         La aplicación de escritorio: planeta, registro y chat (D-035)
│   │   ├── puente.py    Ventana <-> agente: js_api, un hilo fijo, confirmaciones
│   │   ├── primeros_pasos.py  Qué falta para funcionar; guardar y probar claves
│   │   └── preferencias.py    Colores, luz y efectos de la ventana (D-036)
│   ├── obsidian/        Espejo legible de la memoria en el vault
│   │   └── vault.py     Lee y escribe usuario.md y progreso/
│   └── files/           Ficheros que el usuario deja en el buzon
│       └── reader.py    Resuelve la referencia hablada y lo lee como texto
├── native/doomkit/      Núcleo en Rust, opcional (ver native/README.md)
├── obsidian/            El vault en sí (se versiona, ver su README.md)
└── tests/
```

## Por qué `src/`

El paquete está bajo `src/` y no en la raíz para que los tests no puedan
importarlo por accidente desde el directorio de trabajo. Sin esa separación,
`pytest` encuentra `doombot/` estando en la raíz y las pruebas pasan aunque el
paquete esté mal empaquetado; el fallo aparece al instalarlo en la otra
máquina, que es el peor momento posible.

## Las tres capas y su orden

Cada una depende solo de las anteriores. Es lo que permite trabajar en la
lógica sin GPU delante.

1. **Cimientos** — `paths`, `config`, `profiles`. No dependen de nada y son
   los que absorben las diferencias entre equipos.
2. **Contratos** — `backends/base.py`. Interfaces sin implementación. La
   lógica habla con ellas y nunca con un motor concreto, de ahí que el
   portátil pueda usar un modelo pequeño en local o apuntar por red al
   sobremesa sin cambiar una línea.
3. **Dominio** — `memory`, `phrases`, `voice`. Lo propio de D.O.O.M.
4. **Acciones** — `actions`. Depende del dominio (llega por la orden `act` de
   `phrases`) y es la única capa que toca el sistema de verdad: no genera
   texto, ejecuta tareas. Ver D-014 en `docs/decisiones.md`.

## Dónde va cada cosa

| Si es… | Va en… | Porque… |
|---|---|---|
| una ruta | `paths.py` | una sola ruta a mano ata el proyecto a un equipo |
| algo que cambia entre equipos | `.env` | no se versiona |
| algo medido del hardware | `profiles.toml` | son datos, y se revisan sin leer código |
| una interfaz | `backends/base.py` | para poder sustituir el motor |
| estado que genera D.O.O.M | fuera del repo | ver `paths.data_dir()` |
| una capacidad nueva | `identity.py` | el prompt deja de negarla solo |

## El prompt se escribe solo

`identity.py` construye el system prompt a partir de las capacidades
realmente presentes: mira si `memory/`, `phrases/` y `voice/` exponen algo, y
declara únicamente lo que existe.

No es cosmético. Con un prompt fijo, el modelo respondía *"Abrí el navegador"*
a una orden que no puede ejecutar, y *"Te recordaré comprar pan"* sin existir
memoria alguna. Eso impide desarrollar: si promete recordar tanto con memoria
como sin ella, al construirla no hay forma de saber si funciona.

Al implementar una capa, el prompt deja de negarla sin que nadie lo toque.

## Lo que nunca entra al repositorio

`.venv/` (lleva rutas absolutas al Python que lo creó), `.env`, la base de
datos de la memoria, los modelos descargados y las grabaciones. El
`.gitignore` los cubre; `paths.data_dir()` se asegura de que ni siquiera caigan
dentro de la carpeta del proyecto.

## La captura de audio

`voice/capture.py` es la única pieza que toca hardware directamente. Dos
decisiones suyas responden a problemas que no se ven hasta que fallan:

**El micrófono se elige por nombre, no por índice.** El sobremesa expone más de
veinte entradas —Oculus, Steam, VB-Cable, Realtek, A50— repartidas entre cuatro
APIs de Windows, y los índices de PortAudio se desplazan al enchufar o quitar un
USB. Un índice guardado en `.env` acaba apuntando a otro micrófono; un fragmento
del nombre sobrevive. Se configura en `DOOMBOT_AUDIO_INPUT`.

**El umbral de silencio se calibra en cada grabación.** Una constante funciona en
la habitación donde se escribió y falla en cualquier otra: con un ventilador
cerca no detecta silencio nunca, y en una sala callada corta a media frase. Se
mide el ruido de fondo durante los primeros 0,3 s y el umbral sale de ahí, con
un suelo mínimo para que un crujido no cuente como voz.

Además, `Recording` es un gestor de contexto que **borra el fichero al salir**, y
`limpiar_audio_antiguo()` barre lo que deje un cierre brusco. Una grabación solo
interesa hasta que se transcribe, y sin borrado explícito la carpeta de datos
crece sin techo.

Todo lo grabado va a `data_dir()/audio`, nunca dentro del repositorio: es lo que
se ha dicho en voz alta delante del ordenador.

## La capa de acciones

`actions/claude_code.py` delega tareas reales -editar código, ejecutar
comandos- en el propio Claude Code, invocado sin interfaz (`claude -p`), en
vez de escribir un ejecutor de herramientas propio.

**El modo por defecto es `plan`, no uno que ejecute.** Una orden de voz mal
reconocida que dispare código de verdad es un riesgo real y difícil de
deshacer; `plan` hace que el agente proponga sin tocar nada. Pasar a un modo
que ejecuta (`acceptEdits`, `bypassPermissions`) es una decisión que toma
quien instala D.O.O.M en `DOOMBOT_AGENT_PERMISSION_MODE`, nunca el valor de
fábrica.

**`actions/n8n.py` es la segunda forma de actuar, con un riesgo distinto
(D-030).** Dispara workflows de n8n por webhook -"activa el flujo:
`<nombre>`"-, pero D.O.O.M nunca recibe órdenes de n8n, solo se las manda: no
hay servidor nuevo escuchando entradas ajenas. Un webhook no tiene modo
`plan` -ejecuta en cuanto llega la petición-, así que la salvaguarda no es un
nivel de permiso sino una lista blanca en `.env`
(`DOOMBOT_N8N_WORKFLOWS`): un nombre que no esté ahí no dispara nada.

## El agente local

`agent/` es la tercera forma de actuar, y la única con bucle propio (D-033):
recibe una orden escrita y la cumple encadenando herramientas, contando cada
paso. A diferencia de `actions/claude_code.py`, no delega en otro agente: el
bucle es nuestro y el cerebro es cualquier `ToolCaller` de `backends/base.py`
-Ollama o Claude, con la misma conversación neutra y cada backend traduciendo
a su API-.

**Las salvaguardas viven en el bucle, no en cada herramienta**, para que una
herramienta nueva no pueda saltárselas por olvido: lista blanca (solo lo del
catálogo), confirmación de lo irreversible, límite de pasos, salidas
truncadas y resultados viejos enmascarados. Cada herramienta solo declara
*cuándo* es irreversible, en función de sus argumentos: `ls` no se pregunta,
`rm` sí.

**Dónde va una herramienta nueva:** en el módulo de `agent/` que le toque, con
su `narrar` (lo que ve el usuario) y su `confirmar` (cuándo pide permiso), y
añadida a la lista de `montaje.montar()`.

## La aplicación

`python -m doombot ventana` abre D.O.O.M como un programa: su propia ventana
(pywebview), sin navegador a la vista (D-016, D-035). Por dentro dibuja
`ui/ventana/doom.html`: un planeta en WebGL que cambia según el estado y la
herramienta que usa el agente, el registro de lo que piensa y hace, y la
caja para escribirle. El agente corre en el mismo proceso.

**No usa el WebSocket del HUD.** El HUD (D-022) conecta dos programas; aquí
ventana y agente son uno, y `ventana/puente.py` los habla por el `js_api` de
pywebview: JavaScript llama a métodos de Python, y Python pinta con
`DOOM.evento({...})`. Todo el trabajo del agente va en un solo hilo, porque
Playwright solo funciona desde el hilo que lo creó.

**Dónde va un evento nuevo:** se emite desde el puente (`_emitir`) y se pinta
en el `switch` de `DOOM.evento`, en `doom.html`. Abriendo `doom.html#demo`
sin pywebview se simula una orden completa, para diseñar sin agente.

## El vault de Obsidian

`memory/` es rápido pero es una caja cerrada: SQLite con vectores, no algo
que se abra cómodo con un editor. `obsidian/vault.py` conecta ese cerebro
interno con un vault de Obsidian real que vive **dentro del repositorio**
(`paths.VAULT_DIR`, la carpeta `obsidian/` de la raíz) en vez de en una ruta
personal fuera de él.

**Por qué dentro del repo y no en el vault personal de cada uno.** Así el
traspaso entre equipos es el mismo `git pull` de siempre —igual que el resto
del proyecto—, sin exportar ni copiar nada a mano. La contrapartida es que
este vault es *del proyecto*, no el de toda tu vida: si quieres mezclarlo con
tus otras notas, la vía es enlazar o copiar, no apuntar Obsidian aquí y ya.

Dos direcciones, y ninguna sustituye a `memory/` como la fuente que consulta
D.O.O.M al responder:

- **`escribir_perfil`** (D.O.O.M → vault): vuelca a `usuario.md` los hechos
  `kind="perfil"` -los que guarda la orden `recuerda que yo...`-. Se
  sobrescribe entero cada vez: es un espejo, no un diario que se acumula.
- **`sincronizar_perfil`** (vault → D.O.O.M): lee `usuario.md` a mano
  -editado por el usuario, con cualquier editor- y guarda cada línea como un
  hecho de memoria, igual que si se hubiera dicho por voz. Se dispara con
  `/obsidian` en el modo interactivo.
- **`anotar_progreso`**: bitácora en `progreso/AAAA-MM-DD.md`, un fichero por
  día y separado en Mañana/Tarde -corte simple a las 14:00-, para que cada
  sesión de trabajo deje un rastro legible sin desplazarse por meses de
  historial.
