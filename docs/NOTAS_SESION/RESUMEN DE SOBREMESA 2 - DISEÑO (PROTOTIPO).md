  
# Prompt para la sesión paralela: interfaz y voz Copiar íntegro en un chat nuevo. Está pensado para ser autosuficiente: esa sesión no tiene acceso a la conversación principal. --- ## CONTEXTO Estoy construyendo **DOOM**, un asistente personal por voz que funciona 100% en local en mi PC, sin llamadas a la nube. El proyecto va por capas y ya tengo validada la primera. Esta conversación es una **rama paralela** dedicada exclusivamente a dos cosas: la **interfaz gráfica** y la **voz**. La capa de razonamiento y la de audio de entrada las llevo en otro chat, así que no hace falta que las toques. ## MI HARDWARE - CPU AMD Ryzen 7 5800X · 32 GB RAM - GPU NVIDIA RTX 5060 Ti, 16 GB VRAM (**14,8 GiB realmente utilizables**), driver 610.62, CUDA 13.3 - Arquitectura Blackwell, compute capability sm_120 (relevante: algunas librerías aún no la soportan) - Windows 11 Pro · 1 TB SSD ## LO QUE YA ESTÁ DECIDIDO Y MEDIDO (no hace falta rediscutirlo) **Capa 1 — Cerebro.** Ollama 0.33.0 con `gemma4:12b`. Verificado por medición en mi máquina: 100% en GPU, 46,2 tok/s, ~7,8 GB de VRAM ocupados. Se usa el endpoint `/api/chat` (nunca `/api/generate`, que devolvía respuestas vacías). `keep_alive` permanente y un solo modelo residente a la vez. **Presupuesto de VRAM — esta es la restricción que lo gobierna todo.** El LLM se come 7,8 GB de los 14,8 disponibles. Quedan **unos 7 GB** para repartir entre Whisper y el TTS. Cualquier propuesta tuya tiene que caber ahí. **Idioma:** bilingüe, español e inglés. **Capa 2 — Oídos (en marcha en el otro chat):** openWakeWord con el modelo preentrenado `hey_jarvis` + faster-whisper multilingüe. ## LO QUE QUIERO DE ESTA CONVERSACIÓN ### A. La interfaz gráfica Un HUD tipo Siri o JARVIS: **no copiado, pero de esa familia visual**. Un orbe u onda centrada sobre fondo oscuro, que reacciona en tiempo real a la voz, con animaciones fluidas y un color de acento. Decisiones técnicas ya tomadas, dime si las cambiarías: - **`pywebview`** para la ventana: navegador embebido en ventana nativa, con Python llamando a JavaScript y al revés. Elegido porque el resplandor, el desenfoque y las partículas son triviales en Canvas/CSS y un suplicio en Qt o Tkinter, y porque me deja toda la lógica en Python. - `frameless=True`, `transparent=True`, `on_top=True` para el HUD flotante. **La transparencia real en Windows está sin verificar**: si no funciona, necesito alternativa. - **La interfaz no decide nada.** El orquestador emite eventos de cambio de estado más un chorro continuo de amplitud del audio (30-60 veces por segundo). La interfaz solo escucha y anima. Así puedo rehacerla entera sin tocar las capas de audio. **Máquina de estados a representar:**

```
DORMIDO ──wake word──> ESCUCHANDO ──silencio──> PENSANDO ──> HABLANDO ──> DORMIDO
```

Más un estado de ERROR. **Importante sobre mí: no tengo ni idea de diseño y no sé usar herramientas de diseño.** No me mandes a Figma. La forma de trabajar que quiero es que **tú generes prototipos que corran de verdad** —una página HTML que yo abro y veo animándose, con amplitud simulada— y yo te diga qué cambiar. Yo no sé diseñar, pero sí sé juzgar lo que veo. Itera conmigo así. ### B. La voz Bilingüe, y tiene que convivir en VRAM con el LLM y con Whisper. Panorama que ya he mirado, verifícalo y corrígeme si está desactualizado: | Motor | Licencia | Primer audio | Clona voz | |---|---|---|---| | Kokoro-82M | Apache 2.0 | ~45 ms | No | | Chatterbox Multilingual v3 | MIT | — | Sí | | Qwen3-TTS | Apache 2.0 | ~97 ms | Sí, desde 3 s | | XTTS-v2 | CPML (no comercial) | ~320 ms | Sí, el mejor | **Punto de partida: Kokoro**, por velocidad, licencia y consumo bajo. **Restricción que no quiero saltarme:** nada de clonar la voz de una persona real identificable (actores, dobladores, famosos) sin su consentimiento. Descartado también por motivos técnicos: el audio de película lleva música, efectos y reverberación, y da clones sucios. Las vías válidas son voz de catálogo, clonar **mi propia voz**, o bancos de voz con licencia. **El efecto "IA de película" que busco** viene sobre todo de tres cosas que no dependen del modelo: el registro del *system prompt* (pausado, formal, sin coletillas de chatbot), la cadencia (algo más lento de lo normal, pausas limpias) y un procesado ligero del audio (reverberación de sala pequeña, recorte de graves). Quiero que trabajemos eso, no solo el timbre. ### C. Cómo conectar todo Me interesa especialmente resolver bien tres cosas que sé que son las difíciles:

1. **Streaming por frases:** trocear la salida del LLM en frases completas y sintetizar y reproducir mientras el modelo sigue generando, para que empiece a hablar en ~1 s y no en 5.
2. ***Barge-in*:** poder interrumpirlo mientras habla. Es lo que da sensación de producto acabado.
3. **Cancelación de eco:** consecuencia del anterior — si el micrófono sigue abierto mientras el altavoz suena, DOOM se oye a sí mismo y se interrumpe solo.

Tengo apuntadas las librerías `RealtimeTTS` y `RealtimeSTT` (github.com/KoljaB) como candidatas para el troceado y la reproducción en streaming. Evalúa si compensan o si es mejor escribirlo. ## CÓMO QUIERO QUE TRABAJES CONMIGO

1. **Explícame la teoría** de cada componente: qué hace, por qué esa opción y no otra, y qué papel juega. No des por hecho que conozco las herramientas.
2. **Dame el código completo y comentado**, explicando los bloques relevantes.
3. **Vamos paso a paso**, validando cada cosa antes de seguir. Nada de generarlo todo de golpe.
4. **Pídeme confirmación explícita** antes de instalar software o ejecutar comandos con efectos en el sistema.
5. **No te fíes de los benchmarks de blogs.** Cuando haya que elegir, medimos en mi máquina, que es lo que hicimos con el LLM y por eso las cifras de arriba son fiables.
6. **Prioriza herramientas gratuitas y de código abierto.**

## LO QUE **NO** DEBES HACER - No toques las Capas 1 y 2 (LLM y entrada de audio): se llevan en la conversación principal. - No propongas clonar voces de personas reales identificables. - No me mandes a aprender una herramienta de diseño. ## ENTREGABLES QUE ESPERO

1. Un **prototipo del HUD funcionando**, iterado hasta que me convenza, con los cinco estados.
2. Una **decisión de voz razonada y medida** en mi máquina: motor, voz concreta, consumo de VRAM y latencia real hasta el primer audio.
3. El **contrato de comunicación** entre orquestador e interfaz: qué eventos se emiten, con qué formato y a qué frecuencia. Esto es lo que luego tengo que integrar en el proyecto principal.
4. Un **resumen final de decisiones** en formato breve, que pueda pegar en la conversación principal para incorporarlo al registro `docs/decisiones.md` del repositorio.

## PRIMERA TAREA Confirma que entiendes el planteamiento, dime si cambiarías alguna de las decisiones técnicas que ya he tomado (sobre todo `pywebview` y Kokoro), y después **monta el primer prototipo del HUD** para que empecemos a iterar sobre algo que se vea.

El modo automático es ahora el modo de permisos predeterminado de Claude Code.El modo automático permite que Claude gestione los avisos de permisos de forma automática. Claude comprueba cada llamada a herramienta en busca de acciones arriesgadas e inyección de prompt antes de ejecutarla, ejecuta las que considera de menor riesgo y bloquea el resto.[code.claude.com/docs/en/permission-modes](https://code.claude.com/docs/en/permission-modes)

Ejecutado 2 comandos

Entendido. Antes del prototipo, la crítica corta a lo que ya decidiste — y sí, hay dos cosas que cambiaría.

Error al write HUD prototype HTML

Heredoc mangled; uso el escritor directo.

Creado y editado hud.html, usado 3 herramientas+581-1

Enviado

HUD v0.1 — arranca solo con el ciclo completo. Teclas: 1-5 estados, D repetir ciclo, H ocultar panel.

html

hud.html

22,9kB

[](https://claude.ai/api/organizations/41d370b3-9558-4034-ac41-ae7bec68941f/files/4202f299-9239-4de8-8e9f-42bb24b71f9d/contents)

He quedado con el planteamiento claro. Resumo lo que asumo y voy a lo que cambiaría.

---

## Lo que cambiaría de tus decisiones

### 1. `pywebview`: me quedo con él, pero cambio dos cosas

**Sigue siendo la elección correcta.** El resplandor, el desenfoque y el bloom que ves en el prototipo son cuatro líneas de CSS. En Qt esto significa escribir _shaders_ o componer QPixmaps a mano. No hay debate.

**Cambio A — la transparencia se cae de la v1.** En Windows, pywebview usa WebView2 (Edge Chromium) como motor, y ese backend no soporta ventana transparente de verdad. El único apaño real es una ventana _layered_ de Win32 con `LWA_COLORKEY`: elige un color exacto y lo recorta. El problema es que eso es transparencia binaria, sin canal alfa por píxel — y todo el atractivo del HUD está precisamente en el degradado del resplandor, que al desvanecerse hacia el color clave dejaría un halo sucio con borde duro. Peor que no tenerla.

Mi propuesta: **ventana opaca, sin marco, esquinas redondeadas, siempre encima**. El fondo negro con viñeta ya te da la sensación de flotar. Si más adelante quieres el orbe recortado sobre el escritorio, se resuelve con `UpdateLayeredWindow` de Win32, que sí da alfa real, pero es un rodeo que no merece la pena antes de que el diseño esté cerrado.

**Cambio B — pywebview no debería ser el canal de datos.** Empujar amplitud a 60 Hz con `evaluate_js()` es una llamada síncrona por el puente Python↔JS en cada muestra: se atasca y arrastra el hilo de audio.

Lo que propongo: un **WebSocket local en `127.0.0.1`** como único transporte, y pywebview reducido a _marco de ventana_. Tres ventajas concretas:

- Puedes desarrollar el HUD abriéndolo en Chrome, con DevTools, mientras el orquestador corre aparte.
- Si algún día pywebview te estorba, cambias el marco sin tocar una línea de interfaz.
- Encaja con tu principio de que la interfaz no decide nada: el HUD se convierte en un cliente tonto de un flujo de eventos.

### 2. Kokoro: me quedo, con un matiz que cambia tu presupuesto de VRAM

**Kokoro en CPU, no en GPU.** Son 82 millones de parámetros. Tu 5800X lo mueve por encima de tiempo real sin despeinarse, y con eso:

- Liberas **los ~7 GB enteros** para Whisper, en vez de repartirlos.
- Te ahorras el riesgo sm_120 en la capa de voz. PyTorch sobre Blackwell exige builds recientes de CUDA; en CPU ese problema no existe.
- El TTS deja de competir por la GPU con el LLM, que es quien la necesita.

Esto convierte tu restricción principal en un no-problema, y hay que medirlo en tu máquina antes de darlo por bueno.

**El matiz honesto sobre el bilingüismo:** las voces españolas de Kokoro están entrenadas con bastante menos material que las inglesas y el propio proyecto las marca como de calidad inferior. En inglés Kokoro es notablemente bueno; en español hay que escucharlo antes de firmar. Ese es el primer experimento de la parte de voz: generar las mismas cuatro frases en ambos idiomas y que decidas de oído.

**Sobre tu tabla:** las cifras de latencia son de blogs y no me fío, igual que tú. Hay un punto que conviene verificar antes de contarlo como opción: Qwen3-TTS se anunció principalmente como servicio de API de Alibaba, y que exista una versión con pesos abiertos descargables es justo lo que hay que confirmar — si no los hay, incumple tu requisito de 100% local y sale de la lista. Puedo comprobarlo cuando lleguemos ahí.

### 3. `RealtimeTTS` / `RealtimeSTT`: no

Resuelven bien el troceado en frases y la reproducción en streaming, pero arrastran un árbol de dependencias grande y, sobre todo, **esconden justo el control que necesitas para el _barge-in_**. Interrumpir a mitad de frase significa poder vaciar la cola y cortar el stream de salida en el fotograma exacto; con una abstracción encima eso se pelea. Lo que tú necesitas son unas 150 líneas: un troceador de frases, una cola acotada y un `sounddevice.OutputStream` con bandera de parada. Merece la pena escribirlo, mirando cómo lo hace RealtimeTTS.

**Sobre la cancelación de eco**, adelanto la idea para que la tengas en la cabeza: el AEC de verdad (referencia por _loopback_ WASAPI + speexdsp) es la parte más frágil del proyecto. Hay una versión intermedia que da el 80% del efecto por el 10% del trabajo: durante la reproducción no escuchas con Whisper, solo con la wake word. DOOM no dice "hey jarvis" nunca, así que no se autointerrumpe, y tú lo cortas diciendo la palabra. AEC completo después, si hace falta.

---

## El prototipo

`hud.html` — abierto ya en el panel lateral, y se arranca solo con el ciclo completo de conversación. Es un archivo único, sin dependencias, sin conexión a internet.

**Ábrelo también a pantalla completa** para juzgarlo de verdad:

```
start "" "C:\Users\migue\jarvis-local\ui\prototipo\hud.html"
```

**Controles:** `1`–`5` fuerzan cada estado · `D` relanza el ciclo · `H` oculta el panel (así lo ves limpio, que es como quedará).

**Qué he montado y por qué:**

- **Un orbe, no una onda.** La onda plana tipo Siri está muy vista y no distingue estados con claridad. Aquí un anillo cerrado se deforma con la voz: el radio en cada ángulo es la suma de cuatro sinusoides con frecuencias no múltiplas entre sí, así que el patrón no se repite nunca y la deformación parece orgánica en vez de mecánica.
- **El resplandor es una copia desenfocada.** Se dibuja una vez, se copia a dos lienzos a media resolución y CSS los desenfoca. Bloom real, coste casi nulo.
- **Los estados son solo números.** Cada uno es una fila de nueve parámetros, y la transición los interpola. Por eso no hay saltos: el orbe se transforma. Retocar un estado es cambiar un número, no reescribir el dibujo.
- **La amplitud lleva ataque rápido y caída lenta** (40 ms / 190 ms). Sin eso el orbe parpadea en cada pausa entre sílabas y parece roto.
- **`window.DOOM`** ya expone las cuatro funciones del contrato (`setState`, `amplitude`, `caption`, `reset`). El prototipo _es_ la superficie de integración, no un boceto que luego se tira.

**Lo que quiero que me digas** (júzgalo, no lo diseñes):

1. ¿Los cinco estados se distinguen de un vistazo? El que más dudo es PENSANDO frente a ESCUCHANDO.
2. Color: prueba las cinco muestras del panel. Ahora mismo va en cian.
3. ¿Reacciona demasiado o demasiado poco a la voz? Mueve el deslizador de reactividad y dime el número que te gusta.
4. ¿Sobran o faltan partículas? ¿Y el anillo exterior de marcas — aporta o es ruido?
5. Los fps que marque el panel en tu máquina.

Con eso itero la v0.2 antes de tocar nada de voz.

Obvserva la pestaña de google del html que has creado. Realiza pruebas a voluntad para comprobar que funciona todo bien. La idea es c rear esto para el proyecto. Si que es verdad que el diseño quiero que tenga otro estiulo artistico pero vamos pillando la idea. Ahora sería guardar esto dentro del proyecto y continuar dandole controles de voz y texto

en ejecuciónServing prototype on localhost:8080

Funciona: 180 fps, sin errores. Pero está desvaído — los colores se van a blanco. Lo corrijo y le meto los controles de voz y texto.

Editadohud.html+14-11

Ahora los controles de voz y texto.

Editadohud.html+172-2

Ahora lo pruebo estado por estado.

Editado hud.html, usado 3 herramientas+9-6

Ahora sí. Recorro el resto de estados.

Usado 4 herramientas

Detectado un fallo real: la voz de Windows no emite eventos `boundary`, así que el orbe se quedaba casi quieto mientras habla. Lo arreglo.

Editado hud.html, usado 2 herramientas+10-4

Todo el ciclo pasa. Guardo en el proyecto con una nota de uso.

Creado README.md, ejecutado 3 comandos+64-0

Probado en Chrome sobre `http://localhost:8080` (lo serví con `http.server` para que el micrófono funcione; en `file://` Chrome lo bloquea). Recorrí los cinco estados, el ciclo completo y la síntesis de voz.

## Un fallo de verdad, y la corrección de lo que dije a mitad

**El bloom estaba restando luz en vez de sumarla.** Los lienzos de resplandor se superponían en modo de mezcla normal, así que actuaban como una capa semitransparente encima de la escena. Por eso se veía apagado y los colores viraban a gris. Dos arreglos: `mix-blend-mode: screen` en las capas de resplandor, y un tope de luminosidad — por encima de ~72% cualquier matiz vira a blanco y el acento desaparece. La diferencia es la que ves entre estas dos capturas del mismo estado:

Antes era una bola gris difusa; ahora ESCUCHANDO es cian saturado, PENSANDO azul violáceo con arcos orbitando, HABLANDO turquesa más cálido, ERROR rojo con el anillo dentado y temblor. Los cinco se distinguen de un vistazo, que era mi duda.

**Corrijo una cosa que dije hace un momento:** afirmé que las voces SAPI de Windows no emitían eventos `boundary`. Sí los emiten — 17 en una frase con Microsoft Helena. Leí una muestra suelta pillada con el pulso ya decaído y lo di por hecho sin medirlo. El cambio que hice sigue siendo el correcto, pero por otra razón: la envolvente del orbe ahora lleva una base silábica continua y los `boundary` solo acentúan los picos, así que si una voz no los emite el HUD sigue vivo igualmente. Amplitud medida durante el habla: oscila entre 0,45 y 0,73.

## Controles de voz y texto

- **Campo de texto + `Decir`** (o `Ctrl`+`Enter`): recorre el ciclo real — PENSANDO breve, luego HABLANDO sincronizado con la locución, luego DORMIDO al terminar. Verificado de punta a punta.
- **Selector de voz**: encuentra 3 voces locales de 8. Van marcadas `[local]` o `[nube]` — Chrome ofrece voces "Google" que se sintetizan en servidores remotos, y en un proyecto que quiere ser 100% offline no pueden colarse por descuido.
- **Cadencia** (0,60×–1,20×, por defecto 0,88×): es el primer parámetro del "efecto IA de película" que puedes juzgar ya, antes de tocar Kokoro.
- **`Escuchar (mantener)`** o mantener `espacio`: ESCUCHANDO con amplitud del micrófono real. Esto no lo he probado yo porque dispara el diálogo de permisos de Chrome y no voy a concederlo en tu nombre — pruébalo tú, el servidor sigue levantado.
- **No hay reconocimiento de voz.** La Web Speech API de Chrome manda el audio a Google. El micrófono se usa solo para medir amplitud, que es cálculo local.

Todo esto vive en una sección marcada como **banco de pruebas**, separada del HUD. Se tira entera cuando exista el orquestador; `window.DOOM` es lo que se queda.

## Guardado

Rama `capa5-interfaz`, commit `6d8b376`, con `README.md` explicando cómo abrirlo, los atajos y qué mitad del archivo es desechable.

Un aviso: `main` se ha movido desde que empecé — otra sesión ya versionó el prototipo en `74088dc`. Por eso he ido a una rama en vez de a `main` directamente. Para fusionarla:

```
git checkout main && git merge capa5-interfaz
```

El servidor sigue corriendo en 8080 para que puedas probar el micrófono. Cuando termines:

```
netstat -ano | findstr :8080
```

## El estilo artístico

Aquí es donde te toca a ti, y no necesitas saber diseñar: descríbeme la sensación y yo traduzco. Cuatro direcciones concretas por si te sirven de vocabulario:

1. **Instrumento** — menos resplandor, más líneas finas, tipografía técnica, marcas y números alrededor. Se lee como un aparato de precisión, no como una criatura. Es lo más cercano a JARVIS.
2. **Materia** — el orbe deja de ser luz difusa y pasa a tener textura: hebras, filamentos, algo líquido o de humo dentro. Más orgánico, menos digital.
3. **Cristal** — geometría dura, facetas, aristas que reflejan. Frío y afilado, sin nada gaseoso.
4. **Mínimo** — un solo anillo, sin partículas, sin marcas, sin núcleo. Todo el peso en el movimiento y una línea perfecta.

Dime cuál te tira, o simplemente qué te sobra y qué te falta de lo que ves ahora. Con eso monto la v0.2. Y si prefieres cerrar antes la parte de voz y dejar el aspecto para después, también me sirve — lo siguiente ahí sería instalar Kokoro y medir latencia y calidad en español en tu máquina, que requiere tu visto bueno para instalar.