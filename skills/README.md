# Skills de D.O.O.M

Cada carpeta es un modo de conversación de D.O.O.M (D-038), en el formato abierto
[agentskills.io](https://agentskills.io) que eligió D-014: un `SKILL.md` con una cabecera
(`name`, `description`) y las instrucciones debajo.

Lo propio de D.O.O.M va en `metadata` y en `allowed-tools`:

| Campo | Para qué |
|---|---|
| `metadata.titulo` | Nombre que se ve en la ventana |
| `metadata.color` | Color del modo (`#rrggbb`) |
| `metadata.modelos` | Modelos preferidos, en orden (`groq:...`, `gemini`); después, el resto de la cadena |
| `allowed-tools` | Herramientas del agente en este modo, separadas por espacios |

Para añadir un modo basta con una carpeta nueva aquí (o en la carpeta de datos, `skills/`,
para los personales que no se suben a GitHub). Lo que cada modo aprende de ti se guarda aparte,
en la carpeta de datos, no aquí.
