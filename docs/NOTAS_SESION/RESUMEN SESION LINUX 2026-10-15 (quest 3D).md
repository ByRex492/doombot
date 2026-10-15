# Resumen sesión Linux — 2026-10-15 (Quest en 3D)

Rama **`tarea/quest-nativa`** (con `main` fusionado). Decisión: **D-042**.

## Antes de nada: lo del sobremesa no está en GitHub
Ayer la app funcionó en las gafas desde el sobremesa, pero los cambios de la Quest (el
«brazalete», etc.) **no se subieron**. En GitHub, `quest-app/` seguía como en D-041. Esta sesión
rehace la interfaz a partir de la descripción del usuario.

**En el sobremesa, antes de `git pull`**, para no perder lo que haya allí:
```
git status
git switch -c tarea/quest-sobremesa
git add quest-app
git commit -m "Quest: cambios del sobremesa del 14-15/10"
git push -u origin tarea/quest-sobremesa
git switch tarea/quest-nativa
git pull
```
Así lo del sobremesa queda guardado en su propia rama, y se puede comparar o recuperar lo que
valga. Antes hay que poner la identidad de git en ese equipo (`git config --global user.name` y
`user.email`), que la nota de Windows del 15/10 dice que faltaba.

## Qué cambia (D-042)
- **La burbuja, en 3D**: núcleo, resplandor y halo, disco de marcas, tres arcos orbitales y aro,
  todo con geometría propia y colores animados con los 5 estados del HUD. Se coge con una mano y
  se estira con las dos. Debajo, los subtítulos con «Hablar» y «Para».
- **Ventanas como las de Horizon OS**: barra para moverlas, esquinas para cambiar su tamaño, y el
  contenido se recoloca. Al moverlas te siguen mirando. «Tamaños de fábrica» en Ajustes.
- **Hilos de luz** de la burbuja a cada ventana.
- **Brazalete de verdad**: en la muñeca, solo al mirarte la palma, con mano y tamaño ajustables en
  Ajustes.

## Cómo probarlo (en el sobremesa, con las gafas)
1. Lo de arriba, y luego `quest-app\scripts\deploy.ps1`.
2. En las gafas:
   - [ ] La burbuja se ve en 3D: con volumen, arcos girando y color según el estado (al pulsar
     «Hablar» pasa a escuchar; al responder, a hablar).
   - [ ] Coger la burbuja con una mano la mueve; con las dos, cambia de tamaño. Los subtítulos la
     siguen.
   - [ ] Cada ventana tiene barra y esquinas: moverla y cambiarle el tamaño. El texto se recoloca.
   - [ ] Hilos de luz de la burbuja a las ventanas; al esconder ventanas, desaparecen.
   - [ ] Brazalete: solo al girar la palma izquierda hacia la cara. Pulsar sus botones con la otra
     mano. En Ajustes, cambiar a la derecha y de tamaño.
3. Cosas a mirar con ojo: si la burbuja se ve demasiado transparente u opaca sobre el passthrough;
   si el brazalete de la mano derecha queda bien colocado (el espejo es una suposición).

## Verificado aquí
Compila; 6 tests JVM. Sin gafas: nada visual.
