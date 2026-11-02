import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


class _FakeStdin:
    def __init__(self):
        self.writes = []

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass

    def close(self):
        pass


class _FakeStdout:
    def __init__(self, lines):
        self.lines = iter(lines)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.lines)

    def close(self):
        pass


class _FakeProcess:
    def __init__(self, lines):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def bridge(monkeypatch):
    # Arrange: importar el modulo sin crear un proceso real ni usar red.
    # Cargar las anotaciones del SDK antes de sustituir Popen.
    from mcp.server.mcpserver import MCPServer  # noqa: F401

    schemas = [
        {"name": name, "description": ""}
        for name in [
            "leer_sensores", "alimentar", "cambiar_temperatura",
            "encender_apagar_luz", "limpiar_filtro", "cambiar_agua",
            "verificar_salud_peces", "activar_desactivar_filtro",
            "medir_calidad_agua", "agregar_tratamiento", "activar_auto_cuidar",
        ]
    ]
    responses = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": schemas}}) + "\n",
    ]
    process = _FakeProcess(responses)

    class _PopenFactory:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __new__(cls, *args, **kwargs):
            return process

    monkeypatch.setattr("subprocess.Popen", _PopenFactory)
    module_name = "ollama_bridge_under_test"
    sys.modules.pop(module_name, None)

    # Act
    path = Path(__file__).parents[1] / "mcp" / "ollama_bridge.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Assert
    assert module._existing_process is process
    yield module
    module._stop_existing_server()


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        ("cambiar_temperatura", {"objetivo": 24}, None),
        ("cambiar_temperatura", {"objetivo": 30}, None),
        ("activar_desactivar_filtro", {"activar": True}, None),
        ("agregar_tratamiento", {"tipo": "bacteria"}, None),
    ],
)
def test_validate_arguments_accepts_valid_and_boundary_inputs(bridge, name, arguments, expected):
    # Arrange
    # Act
    result = bridge._validate_arguments(name, arguments)

    # Assert
    assert result is expected


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        ("desconocida", {}, "herramienta no permitida"),
        ("cambiar_temperatura", {}, "faltan argumentos: objetivo"),
        ("cambiar_temperatura", {"objetivo": 31}, "objetivo fuera de rango"),
        ("encender_apagar_luz", {"encender": 1}, "encender debe ser booleano"),
        ("alimentar", {"extra": 1}, "contiene argumentos no permitidos"),
        ("agregar_tratamiento", {"tipo": "veneno"}, "tipo no es un tipo valido"),
        ("alimentar", [], "los argumentos deben ser un objeto JSON"),
    ],
)
def test_validate_arguments_rejects_invalid_inputs(bridge, name, arguments, expected):
    # Arrange
    # Act
    result = bridge._validate_arguments(name, arguments)

    # Assert
    assert result == expected


def test_json_body_rejects_non_finite_json(bridge):
    # Arrange
    invalid = {"value": float("nan")}

    # Act
    with pytest.raises(RuntimeError, match="Payload JSON invalido"):
        bridge._json_body(invalid)

    # Assert
    assert True


def test_bridge_validates_model_tool_call_and_calls_simulated_transport(bridge, monkeypatch):
    # Arrange
    monkeypatch.setattr(
        bridge,
        "_discover_action_schemas",
        lambda: {"alimentar": bridge._ACTION_SCHEMAS["alimentar"]},
    )
    monkeypatch.setattr(
        bridge,
        "_ask_model",
        lambda instruction, tools: {
            "message": {"tool_calls": [{"function": {"name": "alimentar", "arguments": {}}}]}
        },
    )
    monkeypatch.setattr(bridge, "_call_existing", lambda name, args: {"content": "ok"})

    # Act
    result = bridge._alimentar_con_ollama(" alimenta al pez ")

    # Assert
    assert result == '"ok"'


def test_bridge_rejects_invalid_model_arguments_without_transport(bridge, monkeypatch):
    # Arrange
    monkeypatch.setattr(bridge, "_discover_action_schemas", lambda: bridge._ACTION_SCHEMAS)
    monkeypatch.setattr(
        bridge,
        "_ask_model",
        lambda instruction, tools: {
            "message": {
                "tool_calls": [{
                    "function": {"name": "cambiar_agua", "arguments": '{"porcentaje": 99}'}
                }]
            }
        },
    )
    called = []
    monkeypatch.setattr(bridge, "_call_existing", lambda *args: called.append(args))

    # Act
    result = bridge._alimentar_con_ollama("cambia mucha agua")

    # Assert
    assert result == "Solicitud rechazada: porcentaje fuera de rango."
    assert called == []


def test_bridge_rejects_empty_instruction(bridge):
    # Arrange
    instruction = "   "

    # Act
    result = bridge._alimentar_con_ollama(instruction)

    # Assert
    assert result == "Error: proporciona una instruccion no vacia."
