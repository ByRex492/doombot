# Capa 4 — Acciones: investigación previa

Estado: **investigación, nada implementado.** Documento de arranque para
trabajar la capa desde cualquiera de los dos equipos.

Fecha: 27/08/2026. Medido en el portátil (`zadiggirl`, GTX 1050, `llama3.2:3b`,
`num_ctx` 4096) salvo donde se indique.

---

## 1. Qué es la Capa 4 y qué NO es

Es la capa que permite a D.O.O.M **hacer cosas** en vez de solo responder:
abrir programas, leer ficheros del disco, ejecutar tareas, controlar el equipo.

Todo lo siguiente es Capa 4, aunque en su momento se hablara de ello por
separado:

- El catálogo de herramientas (skills)
- Leer un PDF u otro fichero local
- Abrir aplicaciones y manejar el sistema
- El bucle de agente que decide qué herramienta usar

**No se empieza hasta cerrar la Capa 3 (voz).** Se apuntó aquí para no
perderlo, no para adelantarlo.

---

## 2. El hallazgo que condiciona toda la capa

Se midieron seis herramientas realistas (`abrir_app`, `leer_fichero`,
`listar_carpeta`, `recordar`, `buscar_memoria`, `volumen`) contra nueve frases,
usando *tool calling* nativo de Ollama con `temperature: 0`.

**`llama3.2:3b` acertó 6 de 9.** Los fallos, literales:

    "Cuanto es 15 por 4"   ->  volumen(nivel=15)
    "Que tal estas"        ->  buscar_memoria(consulta="Que tal estas")
    "Recuerda que manana tengo dentista"  ->  buscar_memoria(consulta="dentista")

Los dos primeros son **acciones no pedidas**: el modelo invocó una herramienta
ante una frase que solo requería responder. `volumen(15)` habría cambiado el
volumen del sistema al preguntar una multiplicación.

Con **solo tres** herramientas el resultado fue **peor: 4 de 9**. Al no existir
la herramienta adecuada, el modelo forzaba una de las disponibles:

    "Cuanto es 15 por 4"   ->  leer_fichero(ruta="15*4")
    "Que tal estas"        ->  leer_fichero(ruta="C:\\...\\archivo.txt")

**Conclusión: la Capa 4 no puede correr con un modelo de 3B.** Es trabajo del
sobremesa con `gemma4:12b`, que tiene soporte nativo de función y el doble de
contexto. Y allí hay que **volver a medirlo**, no darlo por bueno (D-004).

Las fuentes consultadas coinciden: Llama 3.2 3B sirve para clasificación de
triaje, no para planes de varios pasos. El suelo del sector está en 80-90% de
acierto extremo a extremo incluso con modelos capaces.

---

## 3. Coste de contexto: qué formato de herramientas elegir

### Medido en el portátil

Cada entrada de catálogo (nombre + descripción en una línea) cuesta
**20 tokens**. El *system prompt* actual ocupa 185.

| Skills en el catálogo | Tokens | % de 4096 |
|---|---|---|
| 10 | 384 | 9,4 % |
| 25 | 684 | 16,7 % |
| 50 | 1.182 | 28,9 % |
| 100 | 2.180 | 53,2 % |

### Comparativa de los tres formatos

| | Coste al arrancar, por herramienta | Con 10 herramientas en 4096 |
|---|---|---|
| **MCP** | 5.000-6.000 tokens | inviable, desborda 12× |
| **Agent Skills** | 10-20 tokens | ~200 tokens (5 %) |
| **CLI** | 0 — descubre con `--help` | 0 |

**MCP queda descartado por contexto.** Carga *todas* las definiciones al
arrancar vía `tools/list`; un montaje típico consume el 72 % de la ventana
antes de hacer nada. Solo tendría sentido con OAuth centralizado o auditoría,
que aquí no aplican.

**Agent Skills** (agentskills.io) confirma D-014. No es una aplicación ni un
repositorio que se instale: es un **formato de carpeta**.

    mi-skill/
    ├── SKILL.md      obligatorio: frontmatter (name, description) + instrucciones
    ├── scripts/      opcional: código ejecutable
    ├── references/   opcional: documentación auxiliar
    └── assets/       opcional: plantillas

Funciona en tres fases (*divulgación progresiva*):

1. **Descubrimiento** — al arrancar solo se cargan nombre y descripción.
2. **Activación** — cuando la tarea encaja, se lee el `SKILL.md` completo.
3. **Ejecución** — se siguen las instrucciones, ejecutando `scripts/` si los hay.

Esa fase 1 es lo que hace viable tener muchas herramientas con 4096 tokens.

**CLI-first** es la tercera vía y la más barata en contexto: el agente ejecuta
comandos y descubre capacidades con `--help`. Es también la más peligrosa, por
lo visto en el punto 2. Las fuentes indican que MCP local está siendo
sustituido por la pareja **CLI + Skills**: skills para procedimientos de varios
pasos, CLI para operaciones sueltas.

---

## 4. El problema real: las salidas de las herramientas

Las skills no saturan el contexto. Lo que satura son los **resultados**.

Medido en el portátil, contra 4096 tokens:

| Resultado de la herramienta | Tokens | % del contexto |
|---|---|---|
| Listar `src/` recursivo | 785 | 19 % |
| Leer un fichero de código | 2.025 | **49 %** |
| Lista de procesos del sistema | 1.782 | **44 %** |
| Leer `decisiones.md` | 2.025 | **49 %** |

Una sola lectura se come la mitad. Un bucle de agente encadena varias: piensa,
actúa, observa, vuelve a pensar. **Dos lecturas y no queda sitio para la
pregunta original.** Un PDF de 20 páginas rondaría los 15.000 tokens: cuatro
veces el contexto del portátil, el doble del sobremesa.

### Técnicas que resuelven esto

**Observation masking** — tras usar una salida, se sustituye en el historial por
una línea: `"leí store.py, encontré el patrón de validación"`. JetBrains lo
midió contra resumir con LLM: **2,6 % mejor tasa de éxito y 52 % más barato**.
Resumir con LLM salió peor porque suaviza las señales de fallo y el agente
reintenta caminos ya fallidos, alargando las trayectorias un 13-15 %.

Detalle importante de implementación: el enmascarado se aplica **después de que
el agente haya sintetizado** el resultado y **antes** de la siguiente inferencia.
Enmascarar antes de tiempo pierde información que aún hacía falta —por ejemplo,
un test que falla y todavía hay que arreglar—.

Su límite conocido: enmascarar demasiado pronto los materiales de referencia
(esquemas, contratos de API que se consultan repetidamente) baja la tasa de
resolución en torno a un 10 % en modelos con razonamiento extendido.

**Truncado con nota de continuación** — devolver la cabeza y la cola de una
salida enorme con un aviso explícito:

    [mostrando líneas 1-2000 de 50000, usa offset=2001 para continuar]

El modelo sabe que hay más y puede pedirlo. Se combina bien con lo anterior.

**Recuperación en vez de volcado** — un PDF no entra entero: se trocea, se
buscan los fragmentos relevantes y solo entran esos. Es exactamente lo que ya
hace `memory/` con embeddings, así que la pieza ya existe.

---

## 5. Consecuencias de diseño

Nada de esto está decidido; son las conclusiones que se derivan de lo medido.

**Tres compuertas antes de ejecutar nada**, por el 6/9 del punto 2:

1. **El reconocedor de frases decide primero.** `phrases/` ya existe, es
   determinista y resuelve en microsegundos. "Sube el volumen" no debería
   llegar nunca al modelo.
2. **Lista blanca.** El modelo solo puede invocar lo que está en el catálogo, y
   los argumentos se validan antes de ejecutar.
3. **Confirmación hablada para lo irreversible.** Borrar, enviar, comprar,
   instalar.

**El enmascarado del historial hay que diseñarlo desde el principio.** Añadirlo
después obliga a reescribir el orquestador.

**Empezar con 5-10 skills propias**, no importar catálogos masivos. Los ~13.700
de OpenClaw serían ~274.000 tokens: sesenta veces el contexto del portátil.

**Si algún día hicieran falta muchas**, la salida conocida es un catálogo en dos
niveles: agrupar por categoría y cargar solo el grupo relevante. Es un problema
que hoy no existe.

---

## 6. Qué aprovechar de OpenJarvis

Revisado el 27/08/2026 (Apache 2.0, activo). Confirma D-014 y añade dos ideas.

**Lo que se adopta:**

- El estándar `agentskills.io` en vez de inventar un formato propio.
- **Los tres modos de ejecución**: bajo demanda, programado y continuo. Es lo
  que separa un chat de un asistente. Barato preverlo en el orquestador, caro
  añadirlo después. El usuario quiere el modo asistente como principal, con el
  chat como opción secundaria para pasar ficheros o imágenes.
- Su reparto de lenguajes (Python + Rust) confirma que bajar a nativo solo
  donde se mide es lo razonable.

**Lo que NO se adopta**, y sigue vigente lo dicho en D-014: su framework de
agentes, su empaquetado Tauri y su estructura de proyecto. Sustituir el código
propio por el suyo destruiría el propósito del proyecto, que es construirlo
entendiendo cada pieza.

**Sobre "varios agentes de IA":** la idea de un modelo pequeño enrutando a uno
grande **está bloqueada por VRAM**, no por dificultad. D-010 fija
`OLLAMA_MAX_LOADED_MODELS=1` porque en el sobremesa dos modelos llegan a 15.349
de 16.311 MiB y dejan sin sitio a Whisper y al TTS. Multi-modelo exige ambos
residentes: hoy es imposible en las dos máquinas. Se reconsidera si cambia el
hardware.

---

## 7. Coste económico: ninguno

Conviene dejarlo escrito porque se preguntó y es fácil de confundir. D.O.O.M
corre entero en local con Ollama: **los tokens no se facturan**. No hay cuota,
no hay límite mensual, no hay factura por usarlo todo el día.

Lo que se "gasta" es:

- **Tiempo** — 29 tok/s en el portátil, 46,2 en el sobremesa (D-009).
- **Ventana de contexto** — 4096 y 8192 tokens respectivamente.

El límite de la Capa 4 es de diseño, no de presupuesto.

---

## 8. Lo que falta por medir, y dónde

| Qué | Dónde | Por qué |
|---|---|---|
| *Tool calling* de `gemma4:12b` | **sobremesa** | El 6/9 del portátil no se le puede aplicar |
| Cuántas herramientas aguanta antes de degradarse | **sobremesa** | Ninguna fuente da cifras fiables |
| Si `llm_num_ctx = 8192` se respeta de verdad | **sobremesa** | D-003 avisa que Ollama lo fija según VRAM |
| Coste real de un PDF troceado y recuperado | cualquiera | Decide si `memory/` sirve tal cual |

---

## 9. Estado del proyecto al abrir esta rama

Rama creada desde `capa1-reconocimiento-voz` en `1217baf` (*Capa 2 cerrada:
D.O.O.M ya escucha*).

| Capa | Qué es | Estado |
|---|---|---|
| 1 | Cerebro (LLM) | cerrada |
| 2 | Oídos (wake word + STT) | cerrada |
| 3 | Voz (TTS) | siguiente |
| **4** | **Acciones** | **esta rama, solo investigación** |
| 5 | Interfaz (HUD) | prototipo en `capa5-interfaz` |

Lo construido y relevante para esta capa:

- **`phrases/`** — reconocimiento determinista de órdenes, sin modelo. Es la
  primera compuerta del punto 5. Verificado dictando por voz: 10/10.
- **`memory/`** — búsqueda semántica en SQLite. Sirve tal cual para recuperar
  fragmentos de documentos. Techo de ~1.500 recuerdos en Python, ~6.000 con el
  núcleo en Rust compilado.
- **`backends/base.py`** — los tres contratos como `Protocol`. Una herramienta
  nueva no tiene que heredar de nada.
- **`identity.py`** — el *system prompt* se construye según lo que existe. Al
  implementar la capa, la capacidad `actuar` se activará sola.

---

## Fuentes

- [Observation Masking — AgentPatterns.ai](https://agentpatterns.ai/context-engineering/observation-masking/)
- [Efficient context management — JetBrains Research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Is MCP Dead? MCP vs CLI vs Agent Skills — Milvus](https://milvus.io/blog/is-mcp-dead-cli-and-skills-for-ai-agents.md)
- [Agent Skills — especificación](https://agentskills.io)
- [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
