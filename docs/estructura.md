# Estructura del proyecto

Organizado por responsabilidad, no por tecnología. Un módulo se llama como el
problema que resuelve, no como la librería que usa por dentro: así cambiar de
librería no obliga a renombrar nada.

```
doombot/
├── profiles.toml        Perfiles de hardware medidos (datos, no código)
├── pyproject.toml       Dependencias, Python 3.12 fijado, ruff, pytest
├── .env.example         Plantilla de la configuración local
├── .gitattributes       Normaliza finales de línea entre equipos
├── docs/
├── src/doombot/
│   ├── paths.py         Todas las rutas, derivadas en ejecución
│   ├── config.py        Lo que cambia de un equipo a otro
│   ├── profiles.py      Detección de hardware y elección de perfil
│   ├── backends/        Contratos e implementaciones intercambiables
│   ├── memory/          Qué recuerda D.O.O.M
│   ├── phrases/         Frases textuales y órdenes
│   └── voice/           Audio, palabra de activación, síntesis
└── tests/
```

## Por qué `src/`

El paquete está bajo `src/` y no en la raíz para que los tests no puedan
importarlo por accidente desde el directorio de trabajo. Sin esa separación,
`pytest` encuentra `doombot/` estando en la raíz y las pruebas pasan aunque el
paquete esté mal empaquetado; el fallo aparece al instalarlo en la otra
máquina, que es el peor momento posible.

## Las tres capas y su orden

Cada una depende solo de las anteriores. Es lo que permite trabajar en la
lógica sin GPU delante.

1. **Cimientos** — `paths`, `config`, `profiles`. No dependen de nada y son
   los que absorben las diferencias entre equipos.
2. **Contratos** — `backends/base.py`. Interfaces sin implementación. La
   lógica habla con ellas y nunca con un motor concreto, de ahí que el
   portátil pueda usar un modelo pequeño en local o apuntar por red al
   sobremesa sin cambiar una línea.
3. **Dominio** — `memory`, `phrases`, `voice`. Lo propio de D.O.O.M.

## Dónde va cada cosa

| Si es… | Va en… | Porque… |
|---|---|---|
| una ruta | `paths.py` | una sola ruta a mano ata el proyecto a un equipo |
| algo que cambia entre equipos | `.env` | no se versiona |
| algo medido del hardware | `profiles.toml` | son datos, y se revisan sin leer código |
| una interfaz | `backends/base.py` | para poder sustituir el motor |
| estado que genera D.O.O.M | fuera del repo | ver `paths.data_dir()` |

## Lo que nunca entra al repositorio

`.venv/` (lleva rutas absolutas al Python que lo creó), `.env`, la base de
datos de la memoria, los modelos descargados y las grabaciones. El
`.gitignore` los cubre; `paths.data_dir()` se asegura de que ni siquiera caigan
dentro de la carpeta del proyecto.
