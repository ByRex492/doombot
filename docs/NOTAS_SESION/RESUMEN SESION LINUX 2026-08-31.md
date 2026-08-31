# Resumen sesión Linux — 2026-08-31

Sesión de trabajo complementaria desde el equipo Linux (no el sobremesa), siguiendo el
flujo de varias máquinas: todo en ramas `tarea/*`, listo para fusionar en `main` desde el
sobremesa. Nada de esto se ha fusionado todavía — es lo primero que hay que hacer al
retomar.

## Qué se hizo, en orden

### 1. Consolidación de `main`
`capa1-reconocimiento-voz` y `capa5-interfaz` (esta última era solo un puntero parado en
un commit intermedio de la primera, no una rama real) se fusionaron a `main` por
*fast-forward* — sin conflictos, sin fusión de verdad. Se limpiaron ambas ramas del
remoto. Autenticación de `git` cambiada de HTTPS/token (fallaba) a **SSH**, ya configurada
y funcionando.

### 2. Backend de Claude — rama `tarea/backend-claude`
`src/doombot/backends/anthropic.py`: segundo `TextGenerator`, mismo contrato que
`OllamaGenerator`, hablando en crudo con la API de Anthropic vía `httpx` (sin añadir el
SDK). Seleccionable con `DOOMBOT_LLM_BACKEND=anthropic` en `.env`; Ollama sigue siendo el
backend por defecto (D-009: latencia local, funciona sin conexión). 18 tests con
transporte HTTP falso.

### 3. Contexto para Claude Code — rama `tarea/contexto-claude-code`
`CLAUDE.md` en la raíz: se carga solo al abrir el proyecto en cualquier máquina, y explica
el flujo de varias máquinas (ver más abajo) sin que haga falta repetirlo de palabra.

### 4. Capa de acciones — rama `tarea/agente-acciones` (D-014, D-017)
`src/doombot/actions/claude_code.py`: `ClaudeCodeAgent` invoca `claude -p` en modo no
interactivo. **Flags y forma del JSON verificados contra el binario real**, no supuestos.
**Modo por defecto `plan`** (propone, no ejecuta) — decisión de seguridad deliberada: una
orden de voz mal reconocida ejecutando código de verdad es difícil de deshacer. Pasar a un
modo que ejecuta (`acceptEdits`, `bypassPermissions`) es decisión explícita en
`DOOMBOT_AGENT_PERMISSION_MODE`.

Además, en esta misma rama:
- Orden **"ejecuta esto: `<tarea>`"** delega en el agente.
- Orden **"recuerda que yo `<algo>`"** guarda hechos SOBRE EL USUARIO (`kind="perfil"`),
  separados de la memoria general, y **siempre presentes en el prompt** (no filtrados por
  similitud con la pregunta, a diferencia del resto de la memoria).
- `identity.py` ya no miente: la capacidad "actuar" se activa sola en cuanto `actions/`
  expone algo, igual que ya hacía "recordar" con `memory/`.

### 5. Vault de Obsidian — rama `tarea/obsidian` (construida sobre `tarea/agente-acciones`)
`obsidian/` **dentro del repositorio** (no un vault personal fuera de él): así el traspaso
entre máquinas es el mismo `git pull` de siempre, sin exportar ni copiar nada a mano.

- `escribir_perfil` (D.O.O.M → vault): vuelca los hechos `kind="perfil"` a `usuario.md`.
  Se dispara solo tras "recuerda que yo...".
- `sincronizar_perfil` (vault → D.O.O.M): si editas `usuario.md` a mano, la orden de
  consola `/obsidian` lo relee y lo aprende, igual que si lo hubieras dicho.
- `anotar_progreso`: bitácora en `obsidian/progreso/AAAA-MM-DD.md`, separada en
  Mañana/Tarde. Orden **"apunta el progreso: `<algo>`"**. Esta misma nota de sesión se
  escribió con esta función, como prueba de que funciona.

## Ramas pendientes de fusionar, y en qué orden

```
main
├── tarea/backend-claude          (independiente)
├── tarea/contexto-claude-code    (independiente)
└── tarea/agente-acciones         (independiente)
    └── tarea/obsidian            (contiene los commits de agente-acciones)
```

Fusionar `tarea/obsidian` trae automáticamente los commits de `tarea/agente-acciones` —no
hace falta fusionar las dos por separado, aunque hacerlo también es inofensivo (git lo
detecta como ya incluido). El orden entre las cuatro no importa de verdad porque son
líneas independientes, pero **hay un punto de fricción esperado**: `tarea/backend-claude` y
`tarea/agente-acciones`/`tarea/obsidian` tocan los mismos ficheros (`config.py`,
`.env.example`, `chat.py`) para cosas distintas (backend de Claude vs. agente de acciones),
así que al fusionar la segunda tras la primera es probable un conflicto de fusión sencillo
—ambos añaden campos nuevos a `Settings`, no se pisan de contenido— pero hay que revisarlo
a mano, no aceptar automático.

## Ideas planteadas esta sesión, NO implementadas todavía

- **n8n.** Ya corre en este equipo Linux (`~/n8n`, `docker-compose.yml`, puerto 5678,
  `Execute Command` habilitado), pero no está conectado a D.O.O.M de ninguna forma. Falta
  decidir qué automatizaciones tienen sentido (¿D.O.O.M dispara workflows de n8n?, ¿n8n
  dispara acciones de D.O.O.M vía webhook?) antes de construir nada.
- **Enrutador de velocidad/calidad** (Ollama para charla normal, Claude para lo complejo).
  Se discutió pero no se construyó: los criterios de cuándo escalar a Claude son una
  decisión de producto, no algo que debiera decidir yo solo.
- **Confirmación hablada extra antes de que "act" ejecute de verdad**, una vez exista la
  capa de voz completa (wake word + TTS, que hoy no existen en ningún branch). Anotado como
  pendiente en D-017.
- Probar el modo `acceptEdits` del agente de acciones con una tarea real, con Ollama de
  verdad, en el sobremesa — aquí solo se probó con dobles de pruebas.

## Qué hacer primero al retomar en el sobremesa

1. `git fetch` y revisar las cuatro ramas `tarea/*` de arriba.
2. Fusionar (orden sugerido: `tarea/obsidian` primero, luego `tarea/backend-claude` y
   `tarea/contexto-claude-code`), resolviendo a mano el conflicto esperado en
   `config.py`/`.env.example`/`chat.py`.
3. `pytest -m "not hardware"` para confirmar que todo sigue en verde ya con Ollama real
   delante (aquí solo se validó con dobles de prueba, sin GPU).
4. Probar en `chat.py` las tres órdenes nuevas: `recuerda que yo ...`, `ejecuta esto: ...`,
   `apunta el progreso: ...`.
5. Abrir `obsidian/` como vault en la app de Obsidian de verdad y comprobar que
   `usuario.md` y `progreso/` se ven bien.
