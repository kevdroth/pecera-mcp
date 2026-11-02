import atexit
import json
import math
import os
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from typing import Any

from mcp.server.mcpserver import MCPServer


_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "leer_sensores": {"type": "object", "properties": {}, "additionalProperties": False},
    "alimentar": {"type": "object", "properties": {}, "additionalProperties": False},
    "cambiar_temperatura": {
        "type": "object", "properties": {"objetivo": {"type": "number", "minimum": 24, "maximum": 30}},
        "required": ["objetivo"], "additionalProperties": False,
    },
    "encender_apagar_luz": {
        "type": "object", "properties": {"encender": {"type": "boolean"}},
        "required": ["encender"], "additionalProperties": False,
    },
    "limpiar_filtro": {"type": "object", "properties": {}, "additionalProperties": False},
    "cambiar_agua": {
        "type": "object", "properties": {"porcentaje": {"type": "number", "minimum": 10, "maximum": 50}},
        "required": ["porcentaje"], "additionalProperties": False,
    },
    "verificar_salud_peces": {"type": "object", "properties": {}, "additionalProperties": False},
    "activar_desactivar_filtro": {
        "type": "object", "properties": {"activar": {"type": "boolean"}},
        "required": ["activar"], "additionalProperties": False,
    },
    "medir_calidad_agua": {"type": "object", "properties": {}, "additionalProperties": False},
    "agregar_tratamiento": {
        "type": "object", "properties": {
            "tipo": {"type": "string", "enum": ["acondicionador", "medicamento", "bacteria"]}
        },
        "required": ["tipo"], "additionalProperties": False,
    },
    "activar_auto_cuidar": {
        "type": "object", "properties": {"activar": {"type": "boolean"}},
        "required": ["activar"], "additionalProperties": False,
    },
}

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
# The bridge deliberately has one supported model.  Accepting an arbitrary
# environment value made deployments silently target a model with a different
# tool-calling contract.
LLM_MODEL = "qwen35-9b-32k:latest"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
if "LLM_BASE_URL" not in os.environ and os.environ.get("OLLAMA_URL"):
    LLM_BASE_URL = os.environ["OLLAMA_URL"].rsplit("/api/", 1)[0].rstrip("/")
OLLAMA_MODEL = LLM_MODEL
OLLAMA_URL = f"{LLM_BASE_URL}/api/chat"


def _bounded_timeout(name: str, default: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1.0, min(value, maximum)) if math.isfinite(value) else default


_OLLAMA_TIMEOUT = _bounded_timeout("OLLAMA_TIMEOUT", 45.0, 120.0)
_MCP_READ_TIMEOUT = _bounded_timeout("MCP_READ_TIMEOUT", 15.0, 60.0)

SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fish_tank_server.py")
bridge = MCPServer("Pecera LLM Bridge")
_existing_process: subprocess.Popen[str] | None = None
_existing_initialized = False
_existing_lock = threading.RLock()
_existing_stdout: queue.Queue[str | None] | None = None


def _start_existing_server() -> None:
    global _existing_process, _existing_initialized, _existing_stdout
    with _existing_lock:
        if _existing_process is not None:
            raise RuntimeError("El servidor MCP ya fue iniciado.")
        _existing_process = subprocess.Popen(
            [sys.executable, SERVER_PATH], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, text=True, encoding="utf-8",
        )
        _existing_stdout = queue.Queue()
        stdout_queue = _existing_stdout
        process = _existing_process

        def _drain_stdout() -> None:
            assert process is not None and process.stdout is not None
            try:
                for line in process.stdout:
                    stdout_queue.put(line)
            except Exception as exc:
                # A closed pipe (or a reader error on Windows) must wake a
                # pending request instead of leaving it blocked until timeout.
                print(f"Advertencia: no se pudo leer el servidor MCP: {exc}", file=sys.stderr)
            finally:
                stdout_queue.put(None)

        threading.Thread(target=_drain_stdout, name="mcp-stdout-reader", daemon=True).start()
        _existing_initialized = False


def _ensure_existing_server() -> None:
    with _existing_lock:
        if _existing_process is None:
            raise RuntimeError("El servidor MCP no fue iniciado.")
        if _existing_process.poll() is not None:
            raise RuntimeError(
                f"El servidor MCP termino inesperadamente (codigo {_existing_process.returncode})."
            )


def _wait_response(expected_id: int) -> dict[str, Any]:
    """Espera la respuesta JSON-RPC del id esperado, saltando notificaciones."""
    stdout_queue = _existing_stdout
    if stdout_queue is None:
        raise RuntimeError("El lector del servidor MCP no esta disponible.")
    while True:
        try:
            line = stdout_queue.get(timeout=_MCP_READ_TIMEOUT)
        except queue.Empty as exc:
            raise RuntimeError(
                f"El servidor MCP no respondio en {_MCP_READ_TIMEOUT:g} segundos."
            ) from exc
        if line is None:
            raise RuntimeError("El servidor MCP termino antes de responder.")
        if not line.strip():
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(response, dict):
            continue
        method = response.get("method")
        if method is not None and "id" not in response:
            continue
        if response.get("id") != expected_id:
            raise RuntimeError(
                f"Desincronizacion del protocolo MCP: respuesta id={response.get('id')!r}, esperada {expected_id}."
            )
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        return response


def _send_existing(method: str, request_id: int | None, params: dict[str, Any]) -> dict[str, Any]:
    global _existing_initialized
    _ensure_existing_server()
    process = _existing_process
    if process is None or process.poll() is not None or process.stdin is None or process.stdout is None:
        raise RuntimeError("El servidor MCP no esta disponible.")
    if not _existing_initialized:
        process.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "llm-bridge", "version": "1.0"}},
        }) + "\n")
        process.stdin.flush()
        _wait_response(1)
        process.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        ) + "\n")
        process.stdin.flush()
        _existing_initialized = True
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
    if request_id is not None:
        message["id"] = request_id
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    return _wait_response(request_id) if request_id is not None else {}


def _discover_action_schemas() -> dict[str, dict[str, Any]]:
    """Discover the child tools, while allowing only the declared action set."""
    response = _send_existing("tools/list", 2, {})
    tools = (response.get("result") or {}).get("tools") or []
    discovered = {tool.get("name"): tool for tool in tools if tool.get("name") in _ACTION_SCHEMAS}
    missing = set(_ACTION_SCHEMAS) - set(discovered)
    if missing:
        raise RuntimeError(f"El servidor MCP no declaro acciones: {', '.join(sorted(missing))}")
    return {
        name: {**schema, "description": discovered[name].get("description", "")}
        for name, schema in _ACTION_SCHEMAS.items()
    }


def _call_existing(name: str, arguments: dict[str, Any]) -> Any:
    with _existing_lock:
        response = _send_existing("tools/call", 3, {"name": name, "arguments": arguments})
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        return (response.get("result") or response)


def _stop_existing_server() -> None:
    global _existing_process, _existing_initialized, _existing_stdout
    with _existing_lock:
        process = _existing_process
        _existing_process = None
        _existing_initialized = False
        _existing_stdout = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        finally:
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()


atexit.register(_stop_existing_server)


def _initialize_existing_server() -> None:
    """Start and initialize the single child before the bridge accepts requests."""
    with _existing_lock:
        _start_existing_server()
        try:
            response = _send_existing("tools/list", 2, {})
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            tools = (response.get("result") or {}).get("tools") or []
            missing = set(_ACTION_SCHEMAS) - {tool.get("name") for tool in tools}
            if missing:
                raise RuntimeError(
                    f"El servidor MCP no declaro acciones: {', '.join(sorted(missing))}"
                )
        except Exception as exc:
            _stop_existing_server()
            raise RuntimeError(f"No se pudo iniciar el servidor MCP: {exc}") from exc


_initialize_existing_server()


def _validate_arguments(name: str, arguments: Any) -> str | None:
    schema = _ACTION_SCHEMAS.get(name)
    if schema is None:
        return "herramienta no permitida"
    if not isinstance(arguments, dict):
        return "los argumentos deben ser un objeto JSON"
    expected = schema.get("properties", {})
    required = set(schema.get("required", []))
    if set(arguments) - set(expected):
        return "contiene argumentos no permitidos"
    if required - set(arguments):
        return f"faltan argumentos: {', '.join(sorted(required - set(arguments)))}"
    for key, spec in expected.items():
        if key not in arguments:
            continue
        value = arguments[key]
        kind = spec["type"]
        if kind == "boolean" and type(value) is not bool:
            return f"{key} debe ser booleano"
        if kind == "string" and not isinstance(value, str):
            return f"{key} debe ser texto"
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))
                                 or not math.isfinite(value)):
            return f"{key} debe ser un numero finito"
        if "minimum" in spec and value < spec["minimum"] or "maximum" in spec and value > spec["maximum"]:
            return f"{key} fuera de rango"
        if "enum" in spec and value not in spec["enum"]:
            return f"{key} no es un tipo valido"
    return None


def _ollama_chat(instruccion: str, tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = _ollama_payload(instruccion, tools)
    request = urllib.request.Request(
        f"{LLM_BASE_URL}/api/chat", data=_json_body(payload),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_OLLAMA_TIMEOUT) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"No se pudo consultar el proveedor '{LLM_PROVIDER}': {exc}") from exc


def _ask_model(instruccion: str, tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if LLM_PROVIDER == "ollama":
        return _ollama_chat(instruccion, tools)
    raise RuntimeError(f"Proveedor LLM no soportado: {LLM_PROVIDER!r}. Configure LLM_PROVIDER=ollama.")


def _json_body(value: Any) -> bytes:
    """Encode a strict, UTF-8 JSON request body (including on Windows)."""
    try:
        body = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        json.loads(body.decode("utf-8"))
        return body
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RuntimeError(f"Payload JSON invalido: {exc}") from exc


def _ollama_payload(instruccion: str, tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": LLM_MODEL, "stream": False, "keep_alive": "30m",  # keep_alive alto: evita cold-start entre llamadas
        "messages": [
            {"role": "system", "content": "Selecciona como maximo una herramienta de la pecera. "
             "No inventes herramientas ni argumentos."},
            {"role": "user", "content": instruccion},
        ],
        "tools": [{"type": "function", "function": {"name": name, "description": schema.get("description", ""),
                  "parameters": {k: v for k, v in schema.items() if k != "description"}}}
                 for name, schema in tools.items()],
    }


def _alimentar_con_ollama(instruccion: str) -> str:
    """Consulta el proveedor configurado y ejecuta una accion de pecera validada."""
    if not isinstance(instruccion, str) or not instruccion.strip():
        return "Error: proporciona una instruccion no vacia."
    # Serialize the complete exchange: the child has one JSON-RPC stream, so
    # concurrent requests must not interleave writes and responses.
    with _existing_lock:
        try:
            tools = _discover_action_schemas()
            answer = _ask_model(instruccion.strip(), tools)
            calls = (answer.get("message") or {}).get("tool_calls") or []
            if len(calls) != 1:
                return (answer.get("message") or {}).get("content") or "El modelo no solicito una unica accion."
            if not isinstance(calls[0], dict):
                return "Solicitud rechazada: llamada de herramienta invalida."
            function = calls[0].get("function") or {}
            if not isinstance(function, dict):
                return "Solicitud rechazada: funcion invalida."
            name = function.get("name")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    return "Solicitud rechazada: argumentos JSON invalidos."
            error = _validate_arguments(name, arguments)
            if error:
                return f"Solicitud rechazada: {error}."
            result = _call_existing(name, arguments)
            return json.dumps(result.get("content", result) if isinstance(result, dict) else result, ensure_ascii=False)
        except (RuntimeError, ValueError, TypeError) as exc:
            return f"Error: {exc}"


@bridge.tool()
def pecera_ollama_bridge(instruccion: str) -> str:
    """Bridge estable para consultar Ollama y ejecutar una accion validada."""
    return _alimentar_con_ollama(instruccion)


@bridge.tool()
def alimentar_con_ollama(instruccion: str) -> str:
    """Alias compatible del bridge Ollama."""
    return _alimentar_con_ollama(instruccion)


if __name__ == "__main__":
    bridge.run()
