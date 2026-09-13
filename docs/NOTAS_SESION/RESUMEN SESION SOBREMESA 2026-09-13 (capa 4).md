# Resumen sesión sobremesa — 2026-09-13 (Capa 4 · Acciones)

Sesión corta, a petición directa del usuario: activar la Capa 4 (acciones reales, delegadas en
Claude Code — D-014, D-017), que llevaba desde el 01/09 bloqueada por falta del binario
`claude`. Sin cambios de código en el repositorio; todo lo hecho vive en configuración local
(`.env`, no versionado) y en la máquina del usuario.

---

## Lo que se hizo

### 1. Instalado `claude` CLI, por el usuario, en su terminal real

Verificado por las malas: las herramientas de esta sesión corren en un entorno separado del
terminal real del usuario, que sí comparte de verdad el directorio del proyecto (los cambios en
ficheros del repo llegan a ambos lados) pero **no** el resto del sistema — un `npm install -g`
hecho desde esta sesión no llegó a la máquina real del usuario, y costó una vuelta entera
detectarlo. La instalación que cuenta es la que el usuario hizo él mismo, en su PowerShell:

```powershell
npm.cmd install -g @anthropic-ai/claude-code
```

(`npm` a secas fallaba por la política de ejecución de scripts de PowerShell, que bloquea
`npm.ps1`; `npm.cmd` la evita sin tocar ninguna configuración de seguridad).

### 2. `DOOMBOT_AGENT_PERMISSION_MODE=acceptEdits`

Decisión explícita del usuario, no puesta por defecto: edita ficheros sin preguntar, pide
permiso para el resto. Se le explicó la diferencia con `bypassPermissions` (todo sin preguntar,
"solo en una maquina de confianza" según el propio `.env.example`) antes de que eligiera.

### 3. Fallo real encontrado: `subprocess.run(["claude", ...])` no resuelve `.cmd` en Windows

`actions/claude_code.py` invoca el binario por nombre simple. En Windows, `CreateProcess` (lo
que usa `subprocess` por debajo, sin `shell=True`) **no** prueba las extensiones de
`PATHEXT` como hace `cmd.exe` al buscar un ejecutable — así que aunque `claude.cmd` esté en el
`PATH` y funcione perfectamente desde una consola interactiva, `subprocess.run(["claude",...])`
lo falla con `FileNotFoundError`. Se trabajó con la ruta completa:

```
DOOMBOT_AGENT_BINARY=C:\Users\migue\AppData\Roaming\npm\claude.cmd
```

**Pendiente, no resuelto aquí:** esto le va a pasar a cualquiera que instale D.O.O.M en Windows
con `claude` instalado por `npm` y deje `DOOMBOT_AGENT_BINARY=claude` (el valor de
`.env.example`). Una corrección de verdad iría en `actions/claude_code.py` — resolver la ruta
con `shutil.which()` antes de pasarla a `subprocess.run`, que sí conoce `PATHEXT` — pero no se
tocó el código en esta sesión: era una sesión de activar una capacidad para el usuario, no de
tocar `actions/`, y el rodeo por `.env` ya deja la Capa 4 funcionando. Queda anotado para quien
retome ese módulo.

### 4. Verificado con una tarea real, no solo con el diagnóstico

`python -m doombot` (el diagnóstico) solo comprueba que el módulo existe, no que `claude`
responde. Se probó de verdad, en una carpeta fuera del repo:

```powershell
.venv\Scripts\python.exe -c "from doombot.actions.claude_code import ClaudeCodeAgent; ..."
```

Resultado: `success: True`, el fichero pedido se creó con el contenido correcto. La Capa 4
funciona de punta a punta en la máquina del usuario.

---

## Estado

| Capa | Antes | Ahora |
|---|---|---|
| 4 · Acciones (Claude Code) | No: falta el binario | **Sí**, verificado con una tarea real. `acceptEdits` |

Nada que fusionar: todo lo de esta sesión es configuración local (`.env`) y una instalación en
la máquina, no código del repositorio.
