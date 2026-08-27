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
│   ├── identity.py      Qué dice saber hacer, según lo que hay instalado
│   ├── chat.py          Modo interactivo: junta todas las capas en un bucle
│   ├── backends/        Contratos e implementaciones intercambiables
│   ├── memory/          Qué recuerda D.O.O.M
│   ├── phrases/         Frases textuales y órdenes
│   └── voice/           Audio, palabra de activación, síntesis
│       └── capture.py   Micrófono: graba a WAV, detecta silencio, mide nivel
├── native/doomkit/      Núcleo en Rust, opcional (ver native/README.md)
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
| una capacidad nueva | `identity.py` | el prompt deja de negarla solo |

## El prompt se escribe solo

`identity.py` construye el system prompt a partir de las capacidades
realmente presentes: mira si `memory/`, `phrases/` y `voice/` exponen algo, y
declara únicamente lo que existe.

No es cosmético. Con un prompt fijo, el modelo respondía *"Abrí el navegador"*
a una orden que no puede ejecutar, y *"Te recordaré comprar pan"* sin existir
memoria alguna. Eso impide desarrollar: si promete recordar tanto con memoria
como sin ella, al construirla no hay forma de saber si funciona.

Al implementar una capa, el prompt deja de negarla sin que nadie lo toque.

## Lo que nunca entra al repositorio

`.venv/` (lleva rutas absolutas al Python que lo creó), `.env`, la base de
datos de la memoria, los modelos descargados y las grabaciones. El
`.gitignore` los cubre; `paths.data_dir()` se asegura de que ni siquiera caigan
dentro de la carpeta del proyecto.

## La captura de audio

`voice/capture.py` es la única pieza que toca hardware directamente. Dos
decisiones suyas responden a problemas que no se ven hasta que fallan:

**El micrófono se elige por nombre, no por índice.** El sobremesa expone más de
veinte entradas —Oculus, Steam, VB-Cable, Realtek, A50— repartidas entre cuatro
APIs de Windows, y los índices de PortAudio se desplazan al enchufar o quitar un
USB. Un índice guardado en `.env` acaba apuntando a otro micrófono; un fragmento
del nombre sobrevive. Se configura en `DOOMBOT_AUDIO_INPUT`.

**El umbral de silencio se calibra en cada grabación.** Una constante funciona en
la habitación donde se escribió y falla en cualquier otra: con un ventilador
cerca no detecta silencio nunca, y en una sala callada corta a media frase. Se
mide el ruido de fondo durante los primeros 0,3 s y el umbral sale de ahí, con
un suelo mínimo para que un crujido no cuente como voz.

Además, `Recording` es un gestor de contexto que **borra el fichero al salir**, y
`limpiar_audio_antiguo()` barre lo que deje un cierre brusco. Una grabación solo
interesa hasta que se transcribe, y sin borrado explícito la carpeta de datos
crece sin techo.

Todo lo grabado va a `data_dir()/audio`, nunca dentro del repositorio: es lo que
se ha dicho en voz alta delante del ordenador.
