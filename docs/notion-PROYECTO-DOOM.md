# Traspaso del entorno al portátil HP

Checklist operativa. Se ejecuta **en el portátil**, con esta página abierta en el navegador.
El razonamiento de cada decisión está en el repositorio, en `docs/migracion.md`.

Equipo de origen: `BYREX492` · Windows 11 Pro · Ryzen 7 5800X · 32 GB · RTX 5060 Ti
Fecha del inventario: 26/08/2026

---

## Fase 0 — Antes de tocar el portátil

- [ ] **Commitear los cambios pendientes** en el equipo de origen. El bundle solo lleva lo commiteado.
- [ ] **Crear el repositorio privado en GitHub** y hacer `git push -u origin main`. Es el paso que evita tener que repetir todo esto en el futuro. → [Crear repositorio](https://github.com/new)
- [ ] Ejecutar `.\scripts\exportar-equipo.ps1 -Destino E:\traspaso-jarvis` y copiar la carpeta al USB.
- [ ] **Anotar los datos del HP.** Sin esto no se puede elegir el modelo de Ollama (ver Fase 5):

```powershell
Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
```

| Dato | Valor en el HP |
|---|---|
| GPU |  |
| VRAM |  |
| RAM |  |
| Windows |  |

---

## Fase 1 — Requisitos del portátil

- [ ] **Windows 10 versión 1809 o superior, y 64 bits.** VSCode 1.134 no se instala en Windows 8.1 ni en 32 bits. Si el HP no llega, el resto de la checklist no aplica.
- [ ] **Comprobar que existe `winget`:** abrir PowerShell y ejecutar `winget --version`.
  - Si no existe → instalar **App Installer** desde la Microsoft Store, o desde [winget-cli releases](https://github.com/microsoft/winget-cli/releases)
- [ ] Abrir PowerShell **como Administrador** (varios instaladores lo piden).

---

## Fase 2 — Herramientas base

Con `winget` se instalan solas ejecutando `scripts\importar-equipo.ps1`. Los enlaces son la alternativa manual si winget falla.

- [ ] **Git** `2.54.0` — ID: `Git.Git` → [git-scm.com/download/win](https://git-scm.com/download/win)
- [ ] **Python Install Manager** — ID: `Python.PythonInstallManager` → [python.org/downloads/windows](https://www.python.org/downloads/windows/)
- [ ] **Python 3.12** — con el gestor ya instalado: `py install 3.12` (resuelve a **3.12.10**, verificado)
  - Manual: [Python 3.12.10 — instalador Windows 64-bit](https://www.python.org/downloads/release/python-31210/)
  - No sirve el 3.14: el stack de audio/IA no publica *wheels* para esa versión (decisión D-001)
- [ ] **Ollama** `0.33.0` — ID: `Ollama.Ollama` → [ollama.com/download/windows](https://ollama.com/download/windows)
- [ ] **ripgrep** `15.2.0` — ID: `BurntSushi.ripgrep.MSVC` → [ripgrep releases](https://github.com/BurntSushi/ripgrep/releases)
  - Lo necesita la extensión `todo-tree`
- [ ] **7-Zip** `25.00` — ID: `7zip.7zip` → [7-zip.org](https://www.7-zip.org/)

**No se instalan** (son del equipo de origen, no del proyecto): drivers NVIDIA, NVIDIA App, Logitech G HUB, JRE 8, Node.js, Dart SDK.

---

## Fase 3 — VSCode

- [ ] **Instalar la versión exacta 1.134.0** (no la última, para que ambos equipos coincidan):
  [Descarga directa VSCode 1.134.0 x64 User](https://update.code.visualstudio.com/1.134.0/win32-x64-user/stable)
  - Página general por si hace falta otra arquitectura: [code.visualstudio.com/download](https://code.visualstudio.com/download)
- [ ] Marcar **"Añadir a PATH"** durante la instalación.
- [ ] **Cerrar y reabrir PowerShell** después de instalar, o el comando `code` no estará disponible.
- [ ] Copiar `settings.json`, `keybindings.json` y `snippets` desde el USB a `%APPDATA%\Code\User\`
- [ ] **Activar Settings Sync** — es lo que mantiene los dos equipos al día sin repetir este proceso:
  Menú **Manage** (engranaje) o **Accounts** → **"Backup and Sync Settings..."** → iniciar sesión con GitHub
  → [Documentación de Settings Sync](https://code.visualstudio.com/docs/configure/settings-sync)

### Dos ajustes que hay que corregir, no copiar tal cual

- [ ] **`vscode_custom_css.imports`** apunta a `c:/Users/IFC302_2/...vscode-animations-2.0.7/...` — un usuario que no existe y una versión que ya no es la instalada (2.0.8). Ya está roto en el equipo de origen. **Borrar la entrada o corregir la ruta.**
- [ ] **`todo-tree.ripgrep.ripgrep`** es una ruta absoluta con el usuario `migue` incrustado. **Solo funciona si el HP usa el mismo nombre de usuario**; si no, corregir la ruta al `rg.exe` del portátil.

---

## Fase 4 — Extensiones

Las instala `importar-equipo.ps1` con la versión fijada. Con `-SoloJarvis` instala únicamente las 13 marcadas **(núcleo)** — recomendado en un portátil antiguo: ahorra ~1 GB y bastantes procesos en segundo plano.

Comando para una suelta: `code --install-extension <id>@<version>`

**Python (imprescindibles para jarvis-local)**

- [ ] [charliermarsh.ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) - version `2026.74.0` **(nucleo)**
- [ ] [ms-python.debugpy](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy) - version `2026.6.0` **(nucleo)**
- [ ] [ms-python.python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) - version `2026.4.0` **(nucleo)**
- [ ] [ms-python.vscode-pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance) - version `2026.3.1` **(nucleo)**
- [ ] [ms-python.vscode-python-envs](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-python-envs) - version `1.36.0` **(nucleo)**

**Git y control de versiones**

- [ ] [eamodio.gitlens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens) - version `19.0.1` **(nucleo)**
- [ ] [github.vscode-pull-request-github](https://marketplace.visualstudio.com/items?itemName=github.vscode-pull-request-github) - version `0.162.0`
- [ ] [mhutchie.git-graph](https://marketplace.visualstudio.com/items?itemName=mhutchie.git-graph) - version `1.30.0` **(nucleo)**

**Markdown y documentacion**

- [ ] [davidanson.vscode-markdownlint](https://marketplace.visualstudio.com/items?itemName=davidanson.vscode-markdownlint) - version `0.62.1` **(nucleo)**
- [ ] [tomoki1207.pdf](https://marketplace.visualstudio.com/items?itemName=tomoki1207.pdf) - version `1.2.2`
- [ ] [yzhang.markdown-all-in-one](https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one) - version `3.6.3` **(nucleo)**

**Apariencia y ayudas visuales**

- [ ] [be5invis.vscode-custom-css](https://marketplace.visualstudio.com/items?itemName=be5invis.vscode-custom-css) - version `7.5.1`
- [ ] [brandonkirbyson.vscode-animations](https://marketplace.visualstudio.com/items?itemName=brandonkirbyson.vscode-animations) - version `2.0.8`
- [ ] [enkia.tokyo-night](https://marketplace.visualstudio.com/items?itemName=enkia.tokyo-night) - version `1.1.2`
- [ ] [mateoryhr.minecraft-theme](https://marketplace.visualstudio.com/items?itemName=mateoryhr.minecraft-theme) - version `1.0.7`
- [ ] [oderwat.indent-rainbow](https://marketplace.visualstudio.com/items?itemName=oderwat.indent-rainbow) - version `8.3.1`
- [ ] [pkief.material-icon-theme](https://marketplace.visualstudio.com/items?itemName=pkief.material-icon-theme) - version `5.38.1` **(nucleo)**
- [ ] [usernamehw.errorlens](https://marketplace.visualstudio.com/items?itemName=usernamehw.errorlens) - version `3.28.0` **(nucleo)**

**Java (no lo usa este proyecto)**

- [ ] [oracle.oracle-java](https://marketplace.visualstudio.com/items?itemName=oracle.oracle-java) - version `26.0.2`
- [ ] [redhat.java](https://marketplace.visualstudio.com/items?itemName=redhat.java) - version `1.55.0`
- [ ] [vscjava.migrate-java-to-azure](https://marketplace.visualstudio.com/items?itemName=vscjava.migrate-java-to-azure) - version `1.23.0`
- [ ] [vscjava.vscode-gradle](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-gradle) - version `3.18.0`
- [ ] [vscjava.vscode-java-debug](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-java-debug) - version `0.59.0`
- [ ] [vscjava.vscode-java-dependency](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-java-dependency) - version `0.27.6`
- [ ] [vscjava.vscode-java-pack](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-java-pack) - version `0.31.1`
- [ ] [vscjava.vscode-java-upgrade](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-java-upgrade) - version `2.1.2`
- [ ] [vscjava.vscode-maven](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-maven) - version `0.45.3`

**Bases de datos (no lo usa este proyecto)**

- [ ] [geometrislp.gson-toolbox](https://marketplace.visualstudio.com/items?itemName=geometrislp.gson-toolbox) - version `1.1.0`
- [ ] [mtxr.sqltools](https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools) - version `0.28.6`
- [ ] [mtxr.sqltools-driver-mssql](https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools-driver-mssql) - version `0.4.11`
- [ ] [mtxr.sqltools-driver-mysql](https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools-driver-mysql) - version `0.6.7`
- [ ] [mtxr.sqltools-driver-sqlite](https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools-driver-sqlite) - version `0.5.4`
- [ ] [randomfractalsinc.duckdb-sql-tools](https://marketplace.visualstudio.com/items?itemName=randomfractalsinc.duckdb-sql-tools) - version `1.6.0`

**Contenedores y remoto (no lo usa este proyecto)**

- [ ] [ms-azuretools.vscode-containers](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-containers) - version `2.5.0`
- [ ] [ms-azuretools.vscode-docker](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-docker) - version `2.0.0`
- [ ] [ms-vscode-remote.remote-wsl](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl) - version `0.104.3`

**Dart / Flutter (no lo usa este proyecto)**

- [ ] [dart-code.dart-code](https://marketplace.visualstudio.com/items?itemName=dart-code.dart-code) - version `3.140.0`
- [ ] [dart-code.flutter](https://marketplace.visualstudio.com/items?itemName=dart-code.flutter) - version `3.140.0`

**Otras**

- [ ] [dbaeumer.vscode-eslint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) - version `3.0.34`
- [ ] [esbenp.prettier-vscode](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode) - version `12.4.0`
- [ ] [gruntfuggly.todo-tree](https://marketplace.visualstudio.com/items?itemName=gruntfuggly.todo-tree) - version `0.0.226` **(nucleo)**
- [ ] [mikestead.dotenv](https://marketplace.visualstudio.com/items?itemName=mikestead.dotenv) - version `1.0.1` **(nucleo)**
- [ ] [redhat.vscode-yaml](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) - version `1.24.0`
- [ ] [visualstudioexptteam.intellicode-api-usage-examples](https://marketplace.visualstudio.com/items?itemName=visualstudioexptteam.intellicode-api-usage-examples) - version `0.2.9`
- [ ] [visualstudioexptteam.vscodeintellicode](https://marketplace.visualstudio.com/items?itemName=visualstudioexptteam.vscodeintellicode) - version `1.3.2`

---

## Fase 5 — El proyecto

- [ ] **Con repositorio remoto:** `git clone <url-del-repo>` — y listo.
- [ ] **Sin remoto (por USB):** `git clone E:\traspaso-jarvis\jarvis-local.bundle C:\Users\<usuario>\jarvis-local`
- [ ] Crear el entorno virtual **con 3.12 explícito** (si se omite la versión, Windows usa el intérprete por defecto):

```powershell
cd C:\Users\<usuario>\jarvis-local
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

- [ ] Si PowerShell bloquea el script de activación:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

- [ ] **No copiar el `.venv` del equipo de origen.** Contiene rutas absolutas al Python que lo creó; siempre se recrea.

---

## Fase 6 — Ollama y el modelo

> **Esta fase está bloqueada hasta tener los datos de la GPU de la Fase 0.**
> Toda la Capa 1 está calibrada sobre los 14,8 GiB de VRAM del sobremesa. En un portátil antiguo esa premisa no se sostiene, y con ella se caen las decisiones D-004, D-009 y D-010.

- [ ] Instalar Ollama → [ollama.com/download/windows](https://ollama.com/download/windows)
- [ ] Elegir modelo según lo que tenga el HP:

| VRAM del portátil | Modelo | Tamaño | Comando |
|---|---|---|---|
| 8 GB o más | `gemma4:12b` | 7,6 GB | `ollama pull gemma4:12b` |
| 4–6 GB | `qwen3:8b` | 5,2 GB | `ollama pull qwen3:8b` |
| Integrada / sin CUDA | modelo de 3–4B, o no ejecutar el LLM aquí | — | — |

- [ ] **Alternativa recomendada si el HP va justo:** que el portátil **no ejecute el LLM** y apunte al Ollama del sobremesa por red. Se edita y documenta en el portátil, la inferencia la hace la máquina con GPU.
  - En el sobremesa: variable de entorno `OLLAMA_HOST=0.0.0.0`
  - En el portátil: apuntar a la IP del sobremesa
  - Requiere que ambos estén en la misma red

- [ ] **Copiar los modelos por USB en vez de descargarlos** (11,9 GB, mucho más rápido): copiar `%USERPROFILE%\.ollama\models` completo, **con Ollama parado en ambos extremos**.
- [ ] Catálogo de modelos: [ollama.com/library](https://ollama.com/library)

---

## Fase 7 — Verificación

- [ ] `git --version` → debe responder
- [ ] `py -0p` → debe listar **3.12** además de 3.14
- [ ] `code --version` → debe decir **1.134.0**
- [ ] `code --list-extensions | Measure-Object -Line` → 13 con `-SoloJarvis`, 45 en instalación completa
- [ ] `ollama ps` con el modelo cargado → la columna **PROCESSOR** dice qué porcentaje va por GPU
  - Si dice `CPU` o un reparto mixto, el modelo no cabe entero: bajar de tamaño o de cuantización
- [ ] Settings Sync activo y sincronizando

---

## Referencias

- Repositorio del proyecto: *(pegar aquí la URL de GitHub cuando exista)*
- `docs/migracion.md` — el razonamiento completo de este traspaso
- `docs/decisiones.md` — registro de decisiones D-001 a D-011
- `scripts/exportar-equipo.ps1` — genera el paquete en el equipo de origen
- `scripts/importar-equipo.ps1` — lo reconstruye en el portátil
