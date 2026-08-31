# Vault de D.O.O.M

Este vault vive dentro del repositorio a propósito: así `git pull` / `git push`
lo mantienen igual en todas las máquinas, sin exportar ni copiar nada a mano.
Es el mismo mecanismo de traspaso que ya usa el resto del proyecto (ver
`CLAUDE.md` y `docs/decisiones.md`), aplicado a Obsidian.

- **`usuario.md`** — lo que D.O.O.M sabe de ti. Lo genera y actualiza D.O.O.M
  solo (orden `recuerda que yo ...`). Puedes editarlo a mano: con la orden
  `/obsidian` en el modo interactivo, lo relee y aprende lo que hayas añadido,
  igual que si lo hubieras dicho por voz o texto.
- **`progreso/`** — una nota por día (`AAAA-MM-DD.md`), separada en
  Mañana / Tarde, con lo que se ha ido haciendo. La escribe D.O.O.M cuando le
  pides que apunte el progreso.

La configuración propia de la app (`.obsidian/`) no se versiona: cada equipo
tiene la suya, y `.gitignore` la excluye.

Para abrirlo: en Obsidian, "Open folder as vault" → esta carpeta.
