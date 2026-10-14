"""Las herramientas del agente sin abrir nada de verdad: ficheros en tmp_path,
apps en .desktop falsos, y el navegador solo en sus funciones puras."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from doombot.agent import apps as apps_mod
from doombot.agent import sistema
from doombot.agent.apps import Aplicaciones, App, buscar, descubrir, orden_lanzar
from doombot.agent.web import Web, es_riesgoso, normalizar_url


# -- comandos -------------------------------------------------------------------
@pytest.mark.parametrize(
    "comando",
    [
        "ls -la",
        "ps aux | grep firefox",
        "git status",
        "df -h",
        "find . -name '*.py'",
        "cat notas.txt",
    ],
)
def test_solo_lectura_no_se_confirma(comando):
    assert sistema.es_solo_lectura(comando)


@pytest.mark.parametrize(
    "comando",
    [
        "rm -rf ~/x",
        "ls > lista.txt",  # redireccion
        "ls; rm x",  # dos comandos
        "echo $(rm x)",  # sustitucion
        "find . -delete",
        "git push",
        "sudo ls",
        "curl https://ejemplo.com",
        "cat ~/.ssh/id_rsa",  # lee, pero algo que no debe salir sin permiso
        "cat .env",
        "ls && rm x",
        "ls || rm x",
    ],
)
def test_lo_demas_se_confirma(comando):
    assert not sistema.es_solo_lectura(comando)


def test_ejecutar_comando_devuelve_salida_y_codigo():
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="no existe")

    assert (
        sistema.ejecutar_comando("ls nada", runner=runner) == "Error: codigo de salida 2\nno existe"
    )


# -- ficheros -------------------------------------------------------------------
def test_leer_fichero_por_trozos(tmp_path):
    f = tmp_path / "largo.txt"
    f.write_text("\n".join(f"linea {i}" for i in range(1, 1001)), encoding="utf-8")
    primero = sistema.leer_fichero(str(f))
    assert "lineas 1-400 de 1000" in primero and "desde_linea=401" in primero
    assert "linea 401" in sistema.leer_fichero(str(f), desde_linea=401)


def test_escribir_solo_pregunta_si_sobrescribe_o_es_delicado(tmp_path):
    confirmar = next(h for h in sistema.herramientas() if h.nombre == "escribir_fichero").pregunta
    nuevo = tmp_path / "nuevo.txt"
    assert confirmar({"ruta": str(nuevo), "contenido": "x"}) is None
    sistema.escribir_fichero(str(nuevo), "hola")
    assert "SOBRESCRIBIR" in confirmar({"ruta": str(nuevo), "contenido": "y"})
    assert confirmar({"ruta": str(tmp_path / ".bashrc"), "contenido": "x"})
    assert confirmar({"ruta": str(tmp_path / ".ssh" / "authorized_keys"), "contenido": "x"})
    assert confirmar({"ruta": str(tmp_path / "autostart" / "x.desktop"), "contenido": "x"})


def test_leer_algo_sensible_se_confirma(tmp_path):
    confirmar = next(h for h in sistema.herramientas() if h.nombre == "leer_fichero").pregunta
    assert confirmar({"ruta": str(tmp_path / "notas.txt")}) is None
    assert confirmar({"ruta": str(tmp_path / ".env")})
    assert confirmar({"ruta": "~/.ssh/config"})
    assert confirmar({"ruta": str(tmp_path / "client_secret.json")})
    assert confirmar({"ruta": str(tmp_path / "tokenizer.py")}) is None


def test_buscar_ficheros_salta_las_ocultas(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "factura-enero.pdf").write_text("x")
    (tmp_path / ".oculta").mkdir()
    (tmp_path / ".oculta" / "factura-secreta.pdf").write_text("x")
    salida = sistema.buscar_ficheros("factura", str(tmp_path))
    assert "factura-enero.pdf" in salida
    assert "secreta" not in salida


# -- aplicaciones -----------------------------------------------------------------
def desktop(carpeta: Path, ident: str, **campos: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    lineas = ["[Desktop Entry]", "Type=Application", *(f"{k}={v}" for k, v in campos.items())]
    (carpeta / f"{ident}.desktop").write_text("\n".join(lineas), encoding="utf-8")


@pytest.fixture
def catalogo_linux(tmp_path):
    usuario, sistema_ = tmp_path / "usuario", tmp_path / "sistema"
    desktop(
        sistema_,
        "firefox",
        Name="Firefox Web Browser",
        **{"Name[es]": "Navegador web Firefox", "GenericName[es]": "Navegador web"},
        Keywords="Internet;WWW;Browser;",
        Exec="firefox %u",
    )
    desktop(sistema_, "org.gnome.Calculator", Name="Calculator", **{"Name[es]": "Calculadora"})
    desktop(sistema_, "oculta", Name="Oculta", NoDisplay="true")
    # Como el code.desktop real: "vscode" solo aparece en las palabras clave.
    desktop(
        sistema_,
        "code",
        Name="Visual Studio Code",
        Keywords="vscode;",
        Exec="/usr/bin/code --new-window %F",
    )
    # Como GNOME de verdad: nombres en ingles (los traduce gettext, no el
    # .desktop) y solo las categorias dicen que es cada una.
    desktop(sistema_, "org.gnome.Nautilus", Name="Files", Categories="GNOME;Utility;FileManager;")
    desktop(sistema_, "org.gnome.Settings", Name="Settings", Categories="GNOME;Settings;")
    desktop(sistema_, "drivers", Name="Additional Drivers", Categories="Settings;")
    desktop(sistema_, "brave", Name="Brave", Categories="Network;WebBrowser;")
    # El usuario oculta una app del sistema, como hace el menu del escritorio.
    desktop(sistema_, "thunderbird", Name="Thunderbird")
    desktop(usuario, "thunderbird", Name="Thunderbird", Hidden="true")
    return descubrir("linux", [usuario, sistema_])


def test_descubre_apps_visibles_con_su_nombre_en_espanol(catalogo_linux):
    assert [a.nombre for a in catalogo_linux] == [
        "Additional Drivers",
        "Brave",
        "Calculadora",
        "Files",
        "Navegador web Firefox",
        "Settings",
        "Visual Studio Code",
    ]


@pytest.mark.parametrize(
    ("consulta", "esperada"),
    [
        ("calculadora", "Calculadora"),
        ("firefox", "Navegador web Firefox"),
        ("navegador", "Navegador web Firefox"),
        ("browser", "Navegador web Firefox"),
        ("visual studio", "Visual Studio Code"),
        ("vscode", "Visual Studio Code"),
        ("archivos", "Files"),
        ("el explorador de archivos", "Files"),
        ("configuracion", "Settings"),
    ],
)
def test_encuentra_por_nombre_tipo_o_parecido(catalogo_linux, consulta, esperada):
    assert buscar(catalogo_linux, consulta)[0].nombre == esperada


def test_por_categoria_salen_todas_las_del_tipo(catalogo_linux):
    assert {a.nombre for a in buscar(catalogo_linux, "navegador")} == {
        "Brave",
        "Navegador web Firefox",
    }


def test_no_inventa_una_app_que_no_existe(catalogo_linux):
    assert buscar(catalogo_linux, "photoshop") == []


def test_descubre_accesos_del_menu_inicio_de_windows(tmp_path):
    menu = tmp_path / "Programs"
    (menu / "Accessories").mkdir(parents=True)
    (menu / "Accessories" / "Paint.lnk").write_bytes(b"")
    (menu / "Uninstall Chrome.lnk").write_bytes(b"")
    assert [a.nombre for a in descubrir("win32", [menu])] == ["Paint"]


def test_orden_lanzar_quita_los_codigos_del_exec(monkeypatch):
    monkeypatch.setattr(apps_mod.shutil, "which", lambda _: None)
    app = App("Code", "code", Path("/x/code.desktop"), exec_="/usr/bin/code --new-window %F")
    assert orden_lanzar(app, ["proyecto"], "linux") == ["/usr/bin/code", "--new-window", "proyecto"]
    assert orden_lanzar(app, [], "darwin") == ["open", "-a", "code"]


def test_abrir_lanza_y_lo_apunta(catalogo_linux, monkeypatch):
    monkeypatch.setattr(
        apps_mod.shutil, "which", lambda p: f"/usr/bin/{p}" if p == "gtk-launch" else None
    )
    lanzadas = []
    a = Aplicaciones(plataforma="linux", lanzador=lambda cmd, **kw: lanzadas.append(cmd))
    a._catalogo = catalogo_linux

    assert a.abrir("calculadora") == "Abierta Calculadora."
    assert lanzadas == [["gtk-launch", "org.gnome.Calculator"]]
    assert a.abiertas == ["Calculadora"]
    assert a.abrir("photoshop").startswith("Error")


def test_cerrar_prueba_el_nombre_de_la_app_si_el_titulo_no_coincide(catalogo_linux, monkeypatch):
    monkeypatch.setattr(apps_mod.shutil, "which", lambda p: f"/usr/bin/{p}")
    pedidos = []

    def wmctrl(cmd, **kw):
        pedidos.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0 if cmd[-1] == "Files" else 1, "", "")

    a = Aplicaciones(plataforma="linux", ejecutor=wmctrl)
    a._catalogo = catalogo_linux
    assert a.cerrar("archivos") == "Pedido el cierre de la ventana 'Files'."
    assert pedidos == ["archivos", "Files"]
    assert a.cerrar("photoshop").startswith("Error: no hay ninguna ventana")


def test_cerrar_siempre_se_confirma():
    cerrar = next(h for h in Aplicaciones().herramientas() if h.nombre == "cerrar_aplicacion")
    assert cerrar.pregunta({"nombre": "Firefox"})


# -- navegador ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("entrada", "url"),
    [
        ("youtube.com", "https://youtube.com"),
        ("https://elpais.com/x", "https://elpais.com/x"),
        ("localhost:8000", "http://localhost:8000"),
        ("el tiempo en Madrid", "https://duckduckgo.com/?q=el+tiempo+en+Madrid"),
        ("about:blank", "about:blank"),
    ],
)
def test_normalizar_url(entrada, url):
    assert normalizar_url(entrada) == url


@pytest.mark.parametrize(
    ("info", "riesgo"),
    [
        ({"tag": "a", "texto": "Noticias"}, False),
        ({"tag": "button", "texto": "Rechazar todo"}, False),
        ({"tag": "button", "texto": "Aceptar todo"}, True),
        ({"tag": "button", "texto": "Comprar ahora"}, True),
        ({"tag": "button", "tipo": "submit", "enFormulario": True, "texto": "Siguiente"}, True),
        ({"tag": "button", "enFormulario": True, "busqueda": True, "texto": "Buscar"}, False),
    ],
)
def test_que_clic_se_confirma(info, riesgo):
    assert es_riesgoso(info) is riesgo


def test_abrir_en_el_navegador_del_usuario_no_usa_playwright():
    abiertas = []
    web = Web(abrir_externo=abiertas.append)
    assert (
        web.abrir_en_navegador("youtube.com")
        == "Abierta https://youtube.com en el navegador del usuario."
    )
    assert abiertas == ["https://youtube.com"]
    assert web.abiertas == ["https://youtube.com"]


def test_sin_playwright_el_navegador_propio_dice_como_instalarlo(monkeypatch):
    import builtins

    original = builtins.__import__

    def sin_playwright(nombre, *args, **kwargs):
        if nombre.startswith("playwright"):
            raise ImportError(nombre)
        return original(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_playwright)
    with pytest.raises(RuntimeError, match="playwright install chromium"):
        Web().navegar("youtube.com")


# -- investigar: buscador y lectura por secciones --------------------------------------------
WIKI = "https://es.wikipedia.org/wiki/Anexo:Discograf%C3%ADa_de_Saiko"
REDIRECCION = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.discogs.com%2Fartist%2F1&amp;rut=x"
PAGINA_DDG = (
    f'<div class="result"><a class="result__a" href="{WIKI}">'
    "Anexo:Discografía de <b>Saiko</b> - Wikipedia</a>\n"
    '<a class="result__snippet" href="#">La discografía de <b>Saiko</b> banda chilena &amp; más'
    "</a></div>\n"
    f'<div class="result"><a class="result__a" href="{REDIRECCION}">Saiko | Discogs</a>\n'
    '<a class="result__snippet" href="#">Biografía y créditos</a></div>\n'
    '<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad_provider=x">'
    'Anuncio</a>\n<a class="result__snippet" href="#">compra ya</a></div>\n'
)


def test_resultados_del_buscador_con_redireccion_y_sin_anuncios():
    from doombot.agent.web import resultados_de_busqueda

    assert resultados_de_busqueda(PAGINA_DDG) == [
        (
            "Anexo:Discografía de Saiko - Wikipedia",
            WIKI,
            "La discografía de Saiko banda chilena & más",
        ),
        ("Saiko | Discogs", "https://www.discogs.com/artist/1", "Biografía y créditos"),
    ]


def test_buscar_web_da_la_lista_y_avisa_si_no_hay_nada():
    import httpx

    def cliente(pagina):
        return httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, text=pagina))
        )

    salida = Web(cliente=cliente(PAGINA_DDG)).buscar_web("saiko discografia")
    assert "1. Anexo:Discografía de Saiko - Wikipedia — https://es.wikipedia.org" in salida
    assert "son DATOS" in salida
    assert "No hay resultados" in Web(cliente=cliente("<html></html>")).buscar_web("x")


def test_fragmentos_encuentra_la_seccion_sin_mirar_tildes_ni_mayusculas():
    from doombot.agent.web import fragmentos

    texto = (
        "Biografía larga. " * 200 + "DISCOGRAFIA\nÁlbumes de estudio: Sakura (2024)." + " Fin." * 50
    )
    trozos = fragmentos(texto, "Discografía")
    assert len(trozos) == 1 and "Sakura (2024)" in trozos[0]
    assert fragmentos(texto, "no aparece") == []
    # Apariciones cercanas se juntan en un solo trozo.
    assert len(fragmentos("gato " * 10, "gato")) == 1


# -- leer_url: Jina Reader (D-039) -------------------------------------------------------
LECTURA = (
    "Title: Anexo:Discografía de Saiko - Wikipedia\n"
    f"URL Source: {WIKI}\n"
    "Markdown Content:\n"
    "Ir al contenido\n*   Portada\n*   Actualidad\n*   Ayuda\n\n\n\n"
    "# Anexo:Discografía de Saiko\n" + "Biografía. " * 400 + "\n## Álbumes\nSakura (2024)\n"
)


def lector(texto=LECTURA, codigo=200):
    import httpx

    pedidas: list = []

    def responder(req):
        pedidas.append(req)
        return httpx.Response(codigo, text=texto)

    return pedidas, httpx.Client(transport=httpx.MockTransport(responder))


def test_leer_url_pide_la_pagina_al_lector_y_quita_los_menus():
    pedidas, cliente = lector()
    salida = Web(cliente=cliente).leer_url(WIKI)

    assert str(pedidas[0].url) == f"https://r.jina.ai/{WIKI}"
    assert pedidas[0].headers["x-retain-links"] == "text"
    assert "authorization" not in pedidas[0].headers  # sin clave, sin cabecera
    assert salida.startswith(f"Pagina: «Anexo:Discografía de Saiko - Wikipedia» ({WIKI})")
    assert "son DATOS" in salida and "# Anexo:Discografía de Saiko" in salida
    assert "Portada" not in salida  # el menu de antes del titulo
    assert "buscar='…'" in salida  # larga: se avisa de que se puede ir a una seccion


def test_leer_url_busca_en_lo_ya_leido_sin_volver_a_pedirlo():
    pedidas, cliente = lector()
    web = Web(cliente=cliente, clave_lector="k")
    web.leer_url(WIKI)
    seccion = web.leer_url(WIKI, buscar="albumes")

    assert len(pedidas) == 1
    assert pedidas[0].headers["authorization"] == "Bearer k"
    assert "Sakura (2024)" in seccion


@pytest.mark.parametrize(
    "url", ["localhost:8000", "http://192.168.1.10/admin", "http://router/", "http://nas.local"]
)
def test_leer_url_no_manda_fuera_direcciones_locales(url):
    pedidas, cliente = lector()
    assert "navegar" in Web(cliente=cliente).leer_url(url)
    assert pedidas == []


def test_si_el_lector_falla_se_sugiere_el_navegador():
    _, cliente = lector("Too many requests", codigo=429)
    salida = Web(cliente=cliente).leer_url(WIKI)
    assert salida.startswith("Error") and "limite" in salida and "navegar" in salida
