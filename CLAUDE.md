# D.O.O.M — contexto para Claude Code

Asistente de voz local, bilingüe (es/en), construido para funcionar igual en dos equipos sin
que el código note en cuál corre. Este fichero es para orientarse rápido al abrir el proyecto
en cualquier máquina; el README explica cómo arrancarlo.

## Leer primero, en este orden

1. `docs/decisiones.md` — el qué y el porqué de cada decisión de arquitectura, con lo
   descartado. Es la fuente de verdad del proyecto, no el código ni esta sesión de chat.
2. `docs/estructura.md` — por qué está organizado así, y dónde va cada cosa nueva.
3. El fichero más reciente de `docs/NOTAS_SESION/` — dónde se quedó la última sesión de trabajo.
4. `git log --oneline -15` — los mensajes de commit son narrativos a propósito, cuentan el
   porqué, no solo el qué.

## Arquitectura, en una frase

Tres capas (cimientos → contratos → dominio, ver `docs/estructura.md`), donde la lógica habla
solo con los `Protocol` de `backends/base.py` y nunca con una implementación concreta — así una
pieza se sustituye sin tocar a quien la usa. Es el motivo por el que Ollama y Claude conviven
como dos `TextGenerator` intercambiables (`DOOMBOT_LLM_BACKEND`), y por el que el portátil y el
sobremesa comparten el mismo código con perfiles de hardware distintos.

## Trabajo entre varias máquinas

El proyecto se desarrolla desde más de un equipo (el sobremesa, con GPU potente, y otros para
tareas complementarias), cada uno con su propia sesión de Claude Code y sin memoria compartida
entre sí. El repositorio es el único canal de traspaso real:

- **`main`** es la rama de trabajo consolidada — lo que corre en el sobremesa.
- Trabajo complementario desde otra máquina va en una rama `tarea/<algo>`, se empuja, y se
  fusiona a `main` desde el sobremesa cuando esté listo.
- Una decisión de arquitectura nueva es una entrada en `docs/decisiones.md`, no solo un mensaje
  de commit — así se entiende sin reconstruir el razonamiento desde el chat.
- Un "aquí lo dejé" para la siguiente sesión es una nota en `docs/NOTAS_SESION/`.

Al abrir el proyecto en una máquina distinta: `git fetch`, mirar qué ramas `tarea/*` hay
pendientes de fusionar (`git branch -r`), y seguir el orden de lectura de arriba antes de asumir
nada del estado del proyecto.

## Trabajo en paralelo por capas

Varias sesiones de Claude trabajan **a la vez** en capas distintas, cada una en su rama y en su
propia carpeta (`git worktree`). Comprueba en cuál estás con `git branch --show-current` antes
de tocar nada.

| Rama | Carpeta | Escribe en |
|---|---|---|
| `capa/tts` | `C:\Users\migue\doombot-tts` | `src/doombot/tts/` |
| `capa/hud` | `C:\Users\migue\doombot-hud` | `ui/` |
| `main` | `C:\Users\migue\doombot` | integración: fusiona y revisa |

**Las cuatro reglas.** Existen para que las fusiones no se peleen, no por burocracia:

1. **Solo se escribe en la carpeta de la propia capa.** `chat.py`, `config.py`, `paths.py`,
   `profiles.py` y `pyproject.toml` son de integración. Si necesitas algo ahí, dilo en la nota
   de sesión y que lo haga `main`.
2. **Las órdenes se declaran en `tu_paquete/orders.py`**, con `@orden("nombre")` (ver D-020).
   Nunca en `chat.py`. El registro se descubre solo, así que no hay que apuntarse en ningún
   sitio. Si dos capas reclaman la misma orden, el registro revienta al arrancar y lo dice.
3. **Se habla con los `Protocol` de `backends/base.py`, nunca con otra capa.** Ya es la regla
   del proyecto; en paralelo pasa de recomendación a obligación.
4. **Una decisión de arquitectura es una entrada en `docs/decisiones.md` con número reservado
   de antemano** — si no, dos ramas escriben D-021 a la vez y el conflicto cae en el fichero que
   más duele. Reservados: **D-021 para `capa/tts`**, **D-022 para `capa/hud`**.

**Al cerrar sesión, sin excepción:** nota en `docs/NOTAS_SESION/` y `git push` de tu rama. Es lo
único que ve el resto — no hay memoria compartida entre sesiones. Se aprendió por las malas: una
sesión trabajó un día entero sin saber que otra rama ya tenía hecha la palabra de activación.

## Comandos

```
pytest -m "not hardware"    # todo lo que no necesita GPU, Ollama ni microfono
ruff check . && ruff format .
```

Python 3.12 exacto (`requires-python` en `pyproject.toml`): el stack de audio e IA
(`onnxruntime`, `ctranslate2`) no publica *wheels* para 3.13+ todavía.
