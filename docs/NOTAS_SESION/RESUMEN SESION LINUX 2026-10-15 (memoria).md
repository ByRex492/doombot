# Resumen de sesión — Linux (portátil), 15/10/2026 — memoria y perfil

Rama: `tarea/memoria-agente`, sacada de `main`. Decisión: **D-043**.

## Qué se ha hecho

- **Perfil del usuario.**
  - Botón **Perfil** en la cabecera de la ventana. Ahí van:
    - los datos: nombre, cómo llamarte, a qué te dedicas, dónde vives, idiomas, intereses y cómo
      quieres las respuestas;
    - los hechos sueltos;
    - los recuerdos, con buscador y ✕ para borrar.
  - El agente lo lee en **cada orden**, en cualquier modo.
  - Se guarda en `obsidian/usuario.md`, que viaja con git entre equipos y ahora tiene propiedades
    de Obsidian arriba. La voz lo lee igual.
- **Recuerdos.**
  - El agente tiene `recordar`, `buscar_en_memoria` y `olvidar_recuerdo`, sobre `memory.db`.
  - Los que se parecen a la orden le llegan solos, y en el registro salen con ◈.
- **Seguridad.**
  - Apuntar en el perfil siempre pide permiso.
  - `recordar` solo pide permiso si en esa orden se ha leído una página, un fichero o un comando.
  - Contraseñas, claves y datos bancarios no se guardan nunca.
- **`usuario.md` manda.** La voz ya no lo sobrescribe: le añade lo nuevo. Al sincronizar, olvida
  lo que se borró del fichero.
- **Extra nuevo `memoria`** (`fastembed`). En el portátil se ha instalado en `.venv`, y el modelo
  (unos 220 MB) ya está en `~/.local/share/doombot/models`.

## Verificado

- Todos los tests pasan (`pytest -m "not hardware"`) y ruff está limpio.
- `conftest.py` aparta el vault: los tests no tocan el `usuario.md` real.
- Prueba con el modelo real: los recuerdos relacionados llegan en unos 30 ms y los demás no.
- Prueba de punta a punta con la cadena real (Groq sin cuota → Nemotron):
  - apuntó el nombre en el perfil, con permiso;
  - recordó la fecha del examen;
  - en una conversación nueva respondió las dos cosas.
- El panel Perfil, en la demostración (`#demo`).

## Sin verificar

- La ventana real con pywebview: no se ha abierto, porque el usuario la estaba usando.
- En el sobremesa: `usuario.md` editado aquí y traído con `git pull`, y la voz leyéndolo.

## En el sobremesa

1. `git fetch`, revisar `tarea/memoria-agente` y fusionarla a `main`.
2. `pip install -e ".[memoria]"` (si ya está `voice`, no hace falta).
3. Abrir la ventana → **Perfil** y rellenarlo.

**Ojo:** si editas el perfil en un equipo, haz commit de `obsidian/usuario.md` antes de `git pull`
en el otro, o git se negará a traerlo.

Pendiente de antes, sin cambios: la rama `tarea/quest-nativa` (D-041 y D-042) y los cambios de la
Quest que se quedaron sin subir en el sobremesa (ver la nota `(quest 3D)`).
