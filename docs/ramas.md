# Ramas

Dos equipos con capacidades muy distintas trabajan sobre el mismo repositorio.
El reparto no es caprichoso: lo impone el hardware.

| | Sobremesa | Portatil |
|---|---|---|
| GPU | RTX 5060 Ti, 14,8 GiB | GTX 1050, 3 GB |
| Trabajo | Capas nuevas, medicion, modelos grandes | Documentacion, tests, refactores, revision |

## Estructura

    main              Estable. Solo recibe fusiones de ramas terminadas.
    capaN-nombre      Trabajo de capa. Lo abre y lo cierra el SOBREMESA.
    aux/nombre        Trabajo auxiliar del PORTATIL.

## Reglas

1. **El portatil no toca una rama `capaN` que el sobremesa tenga abierta.** Es
   la unica forma de que dos equipos sin coordinacion en tiempo real no se
   pisen. Si el portatil necesita corregir algo de una capa en curso, abre
   `aux/` y se fusiona despues.

2. **`main` no recibe commits directos.** Todo pasa por una rama.

3. **Antes de empezar en cualquier equipo:** `git fetch --all` y mirar que hay.
   El coste de no hacerlo esta documentado en D-012: una jornada entera con la
   unica copia del registro de decisiones en un solo disco.

4. **Nunca `push --force`.** Es lo unico que puede destruir trabajo que no
   tenga copia en el otro equipo.

## Puntos de control

Una rama puede quedarse abierta como punto de control aunque su trabajo no haya
empezado —`capa5-interfaz` lo es—. No estorba y sirve de red si algo se pierde.
