# Traspaso del entorno a un segundo equipo

Cómo reproducir este puesto de trabajo en el portátil HP. El objetivo no es clonar
el disco, sino tener una **receta repetible**: si el traspaso solo se puede hacer
una vez y a mano, dentro de dos semanas los dos equipos habrán divergido.

---

## Inventario real de este equipo (26/08/2026)

Lo que hay que reproducir, medido, no supuesto:

| Bloque | Estado actual |
|---|---|
| VSCode | 1.134.0 (x64, instalación *User*) + **45 extensiones** (~1,2 GB) |
| Proyecto | `jarvis-local`, 1 commit, **sin remoto**, solo documentación (README + `docs/`) |
| Git | 2.54.0.windows.1 |
| Python | **solo 3.14.0**, vía *Python Install Manager* |
| Ollama | 0.33.0 · `gemma4:12b` + `qwen3:8b` · 11,9 GB de blobs |
| Node | 24.11.1 |
| Java | Temurin JDK 25 + JRE 8 |
| Otros | Dart SDK 3.12, ripgrep 15.2, 7-Zip 25 |
| GPU | RTX 5060 Ti · driver 610.62 |

Dos observaciones que salen de este inventario y afectan al traspaso:

- **Python 3.12 no está instalado.** La decisión D-001 lo da por hecho y el README
  lo pide, pero `py -0p` solo lista 3.14. No hay `.venv` ni `requirements.txt`
  todavía, así que aún no ha dado la cara. El portátil debe nacer ya con 3.12.
- **El repositorio no tiene remoto.** Todo el proyecto vive en un único disco.

---

## Estrategia: un remoto, no una copia

El paso que más valor aporta no es copiar nada: es **crear un repositorio remoto
privado** (GitHub) y empujar `main`. A partir de ahí el proyecto deja de ser un
directorio en un disco y pasa a ser algo que ambos equipos sincronizan con
`git pull`. El resto del traspaso ocurre una vez; esto sirve para siempre.

Mientras no exista remoto, `scripts/exportar-equipo.ps1` genera un
**bundle de git**: un fichero único con todos los commits y ramas, que se clona
en destino como si fuera un remoto. Es el plan B correcto para un traspaso
offline por USB, no un sustituto del remoto.

---

## Los cuatro bloques

### 1. El proyecto

- **Con remoto:** `git clone <url>` en el portátil. Fin.
- **Sin remoto:** el bundle que produce el script de exportación.

Ojo: el bundle solo contiene lo **commiteado**. Ahora mismo `docs/decisiones.md`
tiene cambios sin guardar; el script avisa, pero hay que commitear antes.

### 2. VSCode y sus extensiones

Dos caminos, y conviene usar los dos:

**Settings Sync** (recomendado, permanente). Iniciar sesión con la misma cuenta
de GitHub/Microsoft en ambos equipos. Sincroniza extensiones, ajustes, atajos,
snippets y perfiles, y **se mantiene al día solo**. Es la respuesta a "que cuando
termine de trabajar aquí, allí tenga lo último".

**Exportación explícita** (para la primera instalación y como red de seguridad):

- La versión exacta se instala desde la URL versionada de Microsoft:
  `https://update.code.visualstudio.com/1.134.0/win32-x64-user/stable`
- Las extensiones se reinstalan **fijando versión**:
  `code --install-extension charliermarsh.ruff@2026.74.0`

`scripts/importar-equipo.ps1` hace ambas cosas y avisa de las extensiones cuya
versión exacta no esté disponible para ese equipo.

> **Las 45 extensiones no son todas necesarias.** Java, Dart/Flutter, Docker,
> SQLTools y Oracle no tienen nada que ver con este proyecto. El script admite
> `-SoloJarvis` para instalar el subconjunto de Python/Markdown/Git. Un portátil
> antiguo agradece los ~1 GB y los procesos en segundo plano que se ahorra.

**Dos ajustes de `settings.json` que se romperían al copiarlos tal cual:**

- `vscode_custom_css.imports` apunta a
  `file:///c:/Users/IFC302_2/.vscode/extensions/...vscode-animations-2.0.7/...`
  — un usuario que no existe aquí y una versión (2.0.7) que ya no es la instalada
  (2.0.8). Está roto ya en este equipo; copiarlo lo propaga.
- `todo-tree.ripgrep.ripgrep` es una ruta absoluta con el usuario `migue`
  incrustado. Solo funciona si el portátil usa el mismo nombre de usuario.

### 3. Herramientas

Se reinstalan con `winget` por ID, no copiando carpetas. `winget export` genera
el listado del equipo de origen, pero **no conviene importarlo a ciegas**:
arrastraría drivers NVIDIA, NVIDIA App, Logitech G HUB y el JRE 8. El script de
importación instala una lista curada: Git, Python Install Manager (+ 3.12),
Ollama, ripgrep y 7-Zip.

El Python 3.12 se instala con `py install 3.12`, del gestor nuevo. **Verificado**
con `--dry-run` en este equipo: resuelve a **Python 3.12.10** y sale con código 0.

El script refresca el PATH desde el registro entre fases. Sin eso, `git` o `code`
recién instalados no son invocables en la misma sesión de PowerShell, porque un
proceso hereda el PATH al arrancar y no ve los cambios posteriores.

Si el portátil es lo bastante antiguo como para no traer `winget`, hace falta
instalar *App Installer* desde Microsoft Store, o bajar los instaladores a mano.

### 4. Los modelos de Ollama

11,9 GB. Dos opciones:

- **Re-descargar:** `ollama pull gemma4:12b`. Limpio, pero son horas según la línea.
- **Copiar en frío:** llevar `%USERPROFILE%\.ollama\models` completo por USB
  (`-IncluirModelosOllama` en el script de exportación). Con Ollama parado en
  ambos extremos. Mucho más rápido.

---

## El problema serio: la GPU del portátil

Esto no es un detalle de instalación, es una decisión de arquitectura pendiente.

Toda la Capa 1 está calibrada sobre **14,8 GiB de VRAM**. Las decisiones D-004,
D-009 y D-010 se apoyan en esa cifra: `gemma4:12b` ocupa ~7,8 GB, se eligió
frente a `qwen3:8b` porque a 46 tok/s la velocidad "sobraba", y se fijó
`keep_alive: -1` para no pagar los 23 s de recarga.

En un portátil antiguo, con gráficos integrados o una GPU de 4-6 GB, **ninguna de
las tres se sostiene**:

- `gemma4:12b` no cabe en VRAM → Ollama reparte capas a CPU o cae entero a CPU.
- En CPU, un 12B ronda 2-5 tok/s. El propio D-009 fija el umbral en 3-5 tokens
  por segundo de audio: justo ahí es donde la voz **empieza a esperar al modelo**.
  El argumento que hizo ganar a Gemma desaparece.
- `keep_alive: -1` con un modelo en RAM del sistema se come la memoria del equipo.

Lo honesto es tratar el portátil como una **segunda plataforma con su propio
presupuesto**, no como una copia. Opciones, según lo que tenga:

| GPU del portátil | Modelo razonable |
|---|---|
| NVIDIA ≥ 8 GB VRAM | `gemma4:12b` en Q4, igual que aquí |
| NVIDIA 4-6 GB | `qwen3:8b` (5,2 GB) — ya está descargado y medido |
| Integrada / sin CUDA | modelo de 3-4B, o aceptar que el portátil es para **editar y documentar**, no para ejecutar la inferencia |

Hay una cuarta vía que encaja bien con un equipo modesto: que el portátil **no
ejecute el LLM**, y apunte al Ollama del sobremesa por red
(`OLLAMA_HOST=0.0.0.0` en el fijo, y la IP del fijo en el portátil). Trabajo real
en el portátil, inferencia en la máquina que tiene la GPU. Requiere que ambos
estén en la misma red.

**Para decidirlo hace falta un dato que aún no tengo: qué GPU y cuánta RAM tiene
el HP.** Ejecutar esto en el portátil y traer la salida:

```powershell
Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
```

---

## Procedimiento

**En este equipo:**

1. `git add -A ; git commit` — el bundle solo lleva lo commiteado.
2. Crear repo privado en GitHub y `git push -u origin main`. (Recomendado.)
3. `.\scripts\exportar-equipo.ps1 -Destino E:\traspaso-jarvis`
   Añadir `-IncluirModelosOllama` si se van a copiar los 11,9 GB por USB.

**En el portátil HP:**

4. Comprobar antes que el equipo cumple: Windows 10 versión 1809 o superior y
   x64. VSCode 1.134 no se instala en Windows 8.1 ni en 32 bits.
5. `.\importar-equipo.ps1 -Origen E:\traspaso-jarvis -SoloJarvis`
6. `py -3.12 -m venv .venv` y activarlo.
7. Elegir modelo de Ollama según la tabla de arriba.
8. Iniciar sesión en Settings Sync para que a partir de ahí se mantenga solo.

---

## Lo que queda fuera a propósito

- **Drivers y software de periféricos.** NVIDIA App, G HUB: propios de cada máquina.
- **JRE 8 y el stack Java/Dart.** No los usa este proyecto.
- **El `.venv`.** Nunca se copia: contiene rutas absolutas al Python que lo creó.
  Se recrea con `py -3.12 -m venv .venv`.
- **Secretos.** `.env` está en `.gitignore` y no viaja en el bundle. Si más
  adelante existe, se pasa aparte y a mano.
