"""Las rutas no pueden depender del equipo ni del directorio de trabajo."""

from __future__ import annotations

from doombot import paths


def test_project_root_es_el_repositorio():
    assert (paths.PROJECT_ROOT / "pyproject.toml").is_file()
    assert (paths.PROJECT_ROOT / "profiles.toml").is_file()


def test_project_root_no_depende_del_cwd(tmp_path, monkeypatch):
    """Invocar D.O.O.M desde otra carpeta no debe mover la raiz."""
    antes = paths.PROJECT_ROOT
    monkeypatch.chdir(tmp_path)
    assert antes == paths.PROJECT_ROOT


def test_los_datos_no_caen_dentro_del_repositorio(monkeypatch):
    """Si la memoria acabara en el repo, un 'git add -A' la subiria a GitHub."""
    monkeypatch.delenv("DOOMBOT_DATA_DIR", raising=False)
    destino = paths.data_dir().resolve()
    assert paths.PROJECT_ROOT.resolve() not in destino.parents
    assert destino != paths.PROJECT_ROOT.resolve()


def test_data_dir_respeta_el_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DOOMBOT_DATA_DIR", str(tmp_path / "otro"))
    assert paths.data_dir() == tmp_path / "otro"
    assert paths.data_dir().is_dir()


def test_sin_rutas_absolutas():
    """Ningun modulo debe llevar dentro una ruta de un equipo concreto.

    Es el test que evita que el proyecto vuelva a atarse a una maquina, que es
    justo lo que le paso al settings.json heredado del sobremesa.
    """
    sospechosas = (r"C:\Users", "C:/Users/", "/home/", "/Users/")
    fallos = []
    for py in (paths.PROJECT_ROOT / "src").rglob("*.py"):
        texto = py.read_text(encoding="utf-8")
        for linea_n, linea in enumerate(texto.splitlines(), 1):
            if any(s in linea for s in sospechosas):
                fallos.append(f"{py.relative_to(paths.PROJECT_ROOT)}:{linea_n}")
    assert not fallos, "Rutas absolutas encontradas: " + ", ".join(fallos)


def test_sin_temporales_huerfanos():
    """Las carpetas de tempfile no se limpian: una por ejecucion de la bateria.

    Se detectaron 45 MB acumulados en %TEMP% por este motivo. El fixture
    tmp_path de pytest borra las suyas conservando solo las tres ultimas.

    Se analiza el arbol sintactico y no el texto, porque buscar la cadena
    encontraria tambien esta misma explicacion.
    """
    import ast

    prohibidas = {"mkdtemp", "mktemp"}
    sospechosas = []
    for py in (paths.PROJECT_ROOT / "tests").rglob("test_*.py"):
        arbol = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call):
                f = nodo.func
                nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if nombre in prohibidas:
                    sospechosas.append(f"{py.name}:{nodo.lineno}")
    assert not sospechosas, "Usa el fixture tmp_path de pytest, que si se limpia: " + ", ".join(
        sospechosas
    )
