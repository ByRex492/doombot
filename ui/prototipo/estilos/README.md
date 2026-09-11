# Cuatro direcciones visuales

Mismo comportamiento que `ui/prototipo/hud.html` (contrato `window.DOOM`, cinco
estados, banco de pruebas) — lo único que cambia entre estos cuatro ficheros es
`dibujar()` y la paleta/tipografía. Se comparan enseñando, no describiendo.

## Abrir

```bash
py -3.12 -m http.server 8080 --bind 127.0.0.1 --directory C:\Users\migue\doombot-hud\ui\prototipo
```

Y entrar en `http://localhost:8080/estilos/index.html`, que enlaza a las cuatro.
Doble clic también anima, pero bloquea el micrófono (igual que en el prototipo
base).

## Las cuatro

| Fichero | Idea | Qué cambia respecto al prototipo base |
|---|---|---|
| `instrumento.html` | Panel de a bordo, lo más JARVIS | Añade marcas de esquina y un graticule; conserva ticks y arcos orbitales |
| `materia.html` | Orgánico, líquido, con textura | El anillo se rellena (masa líquida, no contorno), zarcillos en vez de ticks/arcos, partículas como brasas |
| `cristal.html` | Facetado, frío, anguloso | Gema de vértices fijos unida con líneas rectas, tabla interior, destello que recorre los bordes, núcleo puntual duro |
| `minimo.html` | Un anillo, todo el peso en el movimiento | Sin ticks, sin arcos, sin núcleo, partículas a 0 por defecto; solo el anillo respira y se engruesa |

Los `ESTADOS` (dormido/escuchando/pensando/hablando/error) son los mismos
números en los cuatro a propósito: así la comparación es solo de dibujo, no de
comportamiento.

## Pendiente

Elegir una, o pedir una mezcla (p. ej. la masa de `materia` con el destello de
`cristal`). Después: cerrar el color final y limpiar los ficheros descartados
antes de que esto sea la versión que sustituye a `hud.html`.
