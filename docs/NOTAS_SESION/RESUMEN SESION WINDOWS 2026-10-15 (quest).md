# Resumen sesión Windows — 2026-10-15 (D.O.O.M para Quest)

Rama **`tarea/quest-nativa`**, en el worktree `C:\Users\luism\doombot-quest`. Lo hecho está en la
ampliación del 15/10 de **D-041** (`docs/decisiones.md`).

## Qué hay nuevo
- Fases 2, 3 y 4 completas: streaming con voz por frases, «hey jarvis», visión con la cámara, n8n
  con confirmación hablada, paneles de información y memoria de hechos.
- Igual que la ventana de escritorio: temas y perfiles de color propios, modos, buscar y leer en
  internet, calcular.
- Arreglos en el agente, la página del móvil y los dos scripts de Windows.

## Instalado en este equipo
- JDK 17.0.20.1 (Temurin) en `%USERPROFILE%\.jdks`; Android SDK en `%LOCALAPPDATA%\Android\Sdk`
  (platform-tools 37, android-34, build-tools 34 y 35). `JAVA_HOME`, `ANDROID_HOME` y adb en el PATH.
- `%USERPROFILE%\.gradle\gradle.properties`: Java con los certificados de Windows (Norton inspecciona
  HTTPS).

## Cómo probarlo en las gafas
`quest-app\scripts\deploy.ps1`, y luego:
- [ ] Ajustes con QR y PIN; claves y cadena desde el móvil. Personalizar: tema, perfil nuevo,
  editarlo y borrarlo, también desde el móvil.
- [ ] «Hey jarvis» baja sus modelos y responde; «Hablar» también. La voz empieza antes de que
  termine el texto.
- [ ] «¿Qué estoy viendo?»: pide la cámara, sale «● CÁMARA» y describe la habitación.
- [ ] «¿Quién es el alcalde de Madrid?»: busca, lee y cita la fuente.
- [ ] «Recuerda que me gusta el café solo» y luego «¿cómo me gusta el café?».
- [ ] «Pon en un panel la lista de la compra»: aparece un panel movible.
- [ ] Un flujo de n8n en la lista: pide confirmación, «sí» lo dispara, «no» no.
- [ ] Modo Ciencias: «energía cinética de 3 kg a 12 m/s» usa calcular.

## Después: ventanas y brazalete
Ventanas curvas, tamaño, minimizar y abrir, y el brazalete de la muñeca izquierda (ampliación 2 de
D-041). Instalada en las Quest 3S del usuario: arranca y va a unos 90 fps (captura por adb).
- [ ] Levantar la muñeca izquierda y mirarla: sale el brazalete. «Fijar» lo deja a la vista.
- [ ] Desde el brazalete: abrir y minimizar cada ventana, «Curvas», «Tamaño −/+», «Micro no».
- [ ] En la cabecera de una ventana: ◠, −, +, _. Al reabrirla, vuelve al mismo sitio.
- [ ] «Esquinas» (experimental): las asas de Meta. Si estorban, se apagan igual.

## Pendiente
- Lo que falle en las gafas: nada de esto se ha ejecutado aún allí.
- El orbe en 3D (malla con shader), si se quiere.
