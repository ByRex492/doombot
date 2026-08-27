# Nucleo nativo

`doomkit` es una extension de Python escrita en Rust. Es **opcional**: el
proyecto funciona sin ella, solo mas despacio en un punto concreto.

## Que hay dentro, y por que solo esto

Solo lo que corre en el camino caliente y **no se puede vectorizar con numpy**.
Esa distincion se midio, no se supuso:

| Funcion | Python | Rust | |
|---|---|---|---|
| nivel RMS de un bloque | 12 us (numpy) | 39 us | **numpy gana** |
| similitud contra 1.000 recuerdos | 99 ms | 22 ms | **Rust gana 4x** |

El nivel de audio ya lo hace numpy en C vectorizado, y cruzar el puente
Python-Rust por cada bloque cuesta mas que la aritmetica que ahorra. La busqueda
en memoria es distinta: es Python puro recorriendo vectores de uno en uno,
porque llegan como BLOB de SQLite y no hay array que vectorizar.

`rms`, `peak`, `nivel` y `suavizar` se quedan compiladas para cuando el HUD
pida amplitud 60 veces por segundo desde un bucle propio, no desde numpy.

## Compilar

Requiere Rust y, en Windows, las Build Tools de Visual Studio con el paquete
de C++.

    winget install --id Rustlang.Rustup --exact
    winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"

Despues, con el entorno virtual del proyecto activo:

    pip install maturin
    cd native/doomkit
    maturin develop --release

Sin compilarlo no hay que hacer nada: `memory/store.py` detecta que falta y usa
el camino en Python.
