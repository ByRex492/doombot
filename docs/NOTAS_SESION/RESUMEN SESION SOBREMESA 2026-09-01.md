# Resumen sesión sobremesa — 2026-09-01

Sesión corta de consolidación. No se escribió funcionalidad nueva: se importó al sobremesa
todo lo que estaba disperso en ramas y se verificó que nada se perdiera por el camino.
El trabajo de diseño del HUD sigue en su propia conversación paralela.

## Qué se hizo

### 1. `main` actualizado y las cinco ramas fusionadas

`main` local iba 5 commits por detrás de `origin/main`; *fast-forward* limpio. Se borró la
rama local `capa1-reconocimiento-voz`, ya contenida en `main` y con su remoto eliminado.

Después se fusionaron en `main` las **cinco** ramas que quedaban fuera:

| Rama | Fecha | Qué traía |
|---|---|---|
| `capa4-acciones` | 27-28/08 | Capa 2 cerrada (`wake.py`, `listener.py`), núcleo Rust, D-008 |
| `tarea/agente-acciones` | 31/08 | Capa de acciones vía Claude Code (D-014, D-017) |
| `tarea/obsidian` | 31/08 | Vault de Obsidian; contiene los commits de la anterior |
| `tarea/backend-claude` | 31/08 | Segundo backend: Claude por API |
| `tarea/contexto-claude-code` | 31/08 | `CLAUDE.md` |

**Hallazgo que conviene no repetir:** la sesión de Linux no sabía que `capa4-acciones`
existía. Su nota afirma que la *wake word* «no existe en ningún branch», y sí existía desde
el 27/08. Dos líneas de trabajo avanzaron en paralelo sin verse. Es el mismo fallo de
coordinación que D-012 ya señaló para el registro de decisiones, ahora con ramas.

### 2. Conflictos resueltos

Cinco en total, todos de ramas que **añaden** cosas distintas en el mismo punto:

- `.gitignore`, `.env.example` — unión. Cada rama aporta su sección.
- `docs/estructura.md` — recomposición manual del árbol. La versión de `capa4-acciones`
  además tenía mal los caracteres del árbol (`└──` seguido de `├──`); quedó corregido.
- `config.py` — unión. `capa4` añade los campos del agente, `backend-claude` los del LLM.
- `chat.py` — el único con decisión real: se conserva `_generador(perfil, cfg)` de
  `backend-claude` en lugar de la llamada directa a `OllamaGenerator`, porque ya elige entre
  los dos backends y el código posterior consultaba `cfg.llm_backend`. Las funciones
  `_contexto_usuario`/`_con_contexto` de `agente-acciones` se conservan intactas.

### 3. Verificación de que no se perdió nada

Comparación fichero a fichero de todo lo que tocó la sesión de Linux contra `main`. Los que
difieren se revisaron buscando pérdidas, no diferencias. Dos falsas alarmas que quedan
explicadas para no volver a investigarlas:

- **Once tests «desaparecidos»** en `test_phrases.py` y `test_identity.py`: son renombrados
  de `capa4-acciones` (`test_reconoce_la_orden_con_muletillas` → `test_orden_con_muletillas`).
  El recuento es idéntico: 38 y 10.
- **Líneas «perdidas»** en `chat.py`: las sustituye `backend-claude`, que es más reciente.

**Suite completa: 242 tests, 236 pasan, 3 omitidos, 3 fallan.** Ningún fallo es regresión de
la fusión; los tres son de integración contra servicios externos (ver más abajo).

---

## Pendiente para la próxima sesión

### A. Empujar la fusión

Nada se ha subido. `main` local va **14 commits por delante** de `origin/main`. Revisar y:

```
git push origin main
```

Si algo no cuadrase, `git reset --hard origin/main` deshace toda la sesión.

Las cinco ramas remotas ya están contenidas en `main` y pueden borrarse del remoto cuando
se haya empujado.

### B. Bug real encontrado: `keep_alive` rompe Ollama en este equipo

**Prioridad alta: el perfil `workstation` no puede hablar con Ollama ahora mismo.**

En `profiles.toml`, el perfil `workstation` tiene `llm_keep_alive = "-1"` **entre comillas**.
Se envía a Ollama como la cadena `"-1"` en vez del número `-1`, y el servidor la rechaza.
Medido con curl contra el Ollama de este equipo:

| Cuerpo enviado | Respuesta |
|---|---|
| `"keep_alive": "-1"` | **400 Bad Request** |
| `"keep_alive": -1` | **200 OK** |

Ollama está sano: responde bien por `/api/chat` con `gemma4:12b`. El endpoint es el
correcto desde D-008; el problema es solo el tipo del valor.

**Decisión que queda por tomar:** si el arreglo va en `profiles.toml` (quitar las comillas,
pero entonces el campo pasa a ser `str | int`) o en `profiles.py`/`ollama.py` al leerlo
(convertir a entero cuando el texto sea un número). La segunda opción es más robusta porque
tolera las dos formas de escribirlo. `llm_keep_alive: str` está anotado como `str` en
`profiles.py:45`, así que el cambio de tipo hay que hacerlo consciente.

### C. Los otros dos tests que fallan

Ninguno bloquea, pero conviene cerrarlos:

- `test_contra_claude_code_real` — no encuentra el binario `claude` en el PATH. Si está
  instalado, ajustar `DOOMBOT_AGENT_BINARY` en `.env` con la ruta completa.
- `test_transcripcion_real` — falta `cublas64_12.dll`. CTranslate2 ve la GPU y ofrece
  `float16` (D-013 lo dejó verificado), pero le falta la librería de CUDA en tiempo de
  ejecución. Es lo que impide dar por cerrada del todo la Capa 2 en este equipo.

### D. Lo que quedó pendiente de la sesión de Linux

Sus puntos 1 a 3 están hechos. Faltan los dos últimos:

1. Probar en `chat.py` las tres órdenes nuevas: `recuerda que yo …`, `ejecuta esto: …`,
   `apunta el progreso: …`.
2. Abrir `obsidian/` como vault en la app de Obsidian y comprobar que `usuario.md` y
   `progreso/` se ven bien.

### E. Ideas anotadas, sin construir

Vienen de la sesión de Linux y siguen sin decidirse:

- **n8n.** Corre ya en el equipo Linux (`~/n8n`, puerto 5678) pero no está conectado a
  D.O.O.M de ninguna forma. Falta decidir la dirección: ¿D.O.O.M dispara *workflows* de n8n,
  o n8n dispara acciones de D.O.O.M por *webhook*? Decidir antes de escribir nada.
- **Enrutador de velocidad/calidad** entre Ollama y Claude. Los criterios de cuándo escalar
  son decisión de producto.
- **Confirmación hablada** antes de que el agente ejecute de verdad, cuando exista la capa
  de voz completa. Anotado en D-017.
- Probar el modo `acceptEdits` del agente con una tarea real y Ollama de verdad.

### F. Capa 5 (interfaz y voz), en su conversación aparte

El prototipo del HUD está en `ui/prototipo/hud.html` con sus cinco estados, el contrato
`window.DOOM` y un banco de pruebas de voz. Pendiente allí: cerrar el estilo artístico
—el actual fija el comportamiento, no el aspecto— y elegir motor de TTS midiendo Kokoro en
esta máquina.
