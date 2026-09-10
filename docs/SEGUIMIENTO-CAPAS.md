# Seguimiento de las capas en paralelo

Cómo saber por dónde van `capa/tts` y `capa/hud` sin interrumpirlas, y qué pedirles cuando
haga falta. Se lee desde integración (`main`).

---

## 1. El parte automático

No pregunta nada a nadie: lo lee todo del repositorio.

```
powershell -ExecutionPolicy Bypass -File scripts\estado-capas.ps1
```

De cada rama dice cuántos commits lleva por delante, qué ficheros ha tocado, si ha escrito ya
su decisión y su nota de sesión, si tiene cambios sin commitear y si ha subido a GitHub.

**Lo que de verdad justifica el script** es una línea que ojalá nunca aparezca:

```
AVISO: ha escrito en ficheros de integracion:
  src/doombot/chat.py
-> revisar a mano antes de fusionar
```

Esa es la única cosa que puede estropear una fusión. Verificado con un commit de prueba que
invadía `chat.py` a propósito: lo detecta.

Un `NO - falta git push` también merece atención: mientras no suban, su trabajo existe en una
sola carpeta y nadie más lo ve.

---

## 2. El prompt de seguimiento

Para pegar en cualquiera de los dos chats cuando quieras un parte. Está pensado para que la
respuesta sea corta y comprobable, no un resumen amable.

> Dame un parte breve, sin adornos:
>
> 1. **Qué has terminado** y está commiteado.
> 2. **Qué has medido en esta máquina**, con las cifras. Si no has medido nada todavía, dilo.
> 3. **Qué te falta** para cerrar tu encargo.
> 4. **Qué necesitas de integración**: cualquier cambio en `chat.py`, `config.py`, `paths.py`,
>    `backends/base.py` o `pyproject.toml`, que tú no puedes tocar.
> 5. **Has hecho `git push` de tu rama?** Si no, hazlo ahora.
> 6. **Algo que hayas descubierto y contradiga lo que dan por hecho las otras sesiones.**
>
> Si has tomado alguna decisión de arquitectura, confirma que está escrita en
> `docs/decisiones.md` con tu número reservado y no con otro.

El punto 6 es el que importa más de lo que parece. El fallo de coordinación que ya nos pasó una
vez —una sesión trabajando un día entero sin saber que otra rama tenía hecha la palabra de
activación— no se evita preguntando por el progreso, sino preguntando por lo que rompe las
suposiciones ajenas.

---

## 3. Cuando una rama esté lista

```
powershell -ExecutionPolicy Bypass -File scripts\estado-capas.ps1
git merge --no-ff capa/tts
```

`--no-ff` a propósito: deja un commit de fusión que marca dónde entró cada capa, y eso hace que
revertir una entera sea un solo comando si hiciera falta.

Después de fusionar, propagar a la otra rama para que no se quede atrás:

```
git push origin main
git -C C:\Users\migue\doombot-hud merge --ff-only main
```

---

## 4. Lo que integración ya espera recibir

Anotado aquí para no olvidarlo: son cosas que esas ramas **no pueden hacer ellas mismas**
porque tocan ficheros comunes, así que llegarán como petición en su nota de sesión.

| De | Qué | Dónde va |
|---|---|---|
| `capa/tts` | El valor medido de `_ESCALA_NIVEL` (hoy 3,0, puesto a ojo) | `backends/base.py` |
| `capa/tts` | Dependencias de Kokoro, probablemente como extra `voice-tts` | `pyproject.toml` |
| `capa/hud` | Dependencia de `pywebview` y del servidor WebSocket | `pyproject.toml` |
