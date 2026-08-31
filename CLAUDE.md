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

## Comandos

```
pytest -m "not hardware"    # todo lo que no necesita GPU, Ollama ni microfono
ruff check . && ruff format .
```

Python 3.12 exacto (`requires-python` en `pyproject.toml`): el stack de audio e IA
(`onnxruntime`, `ctranslate2`) no publica *wheels* para 3.13+ todavía.
