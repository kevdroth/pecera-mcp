import os
import json
import math
import random
import logging
import threading
import time
from collections import deque
from flask import Flask, jsonify, send_from_directory
from mcp.server.mcpserver import MCPServer

logging.getLogger("werkzeug").disabled = True
os.environ["WERKZEUG_RUN_MAIN"] = "true"

mcp = MCPServer("Pecera")
app = Flask(__name__)
lock = threading.Lock()

GRID_SIZE = 5
AUTO_CARE_TARGETS = {
    "temp": 26.0, "ammonia": 0.0, "nitrite": 0.0, "nitrate": 10.0,
    "ph": 7.2, "oxygen": 85.0, "clarity": 100.0, "water_level": 100.0,
}

STATE = {
    "temp": 26.0, "ph": 7.2, "ammonia": 0.0, "nitrite": 0.0,
    "nitrate": 10.0, "oxygen": 85.0, "water_level": 100.0, "clarity": 95.0,
    "heater_temp": 26.0, "heater_on": True, "filter_on": True, "light_on": True,
    "auto_mode": False,
    "sim_hour": 8, "sim_minute": 0, "outdoor_temp": 24.0,
    "last_action": "Pecera iniciada",
}

FISH = {"x": 2, "y": 2, "hunger": 20, "stress": 5, "health": 100, "alive": True}

FOOD = []
tick_count = [0]

GRID = {
    "size": GRID_SIZE,
    "heater": [(0, 0)],
    "filter": [(4, 0)],
    "plants": [(1, 4), (3, 4), (1, 3), (3, 3)],
    "rocks": [(2, 4)],
}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def bfs(start, goal):
    if start == goal:
        return []
    q = deque([(start, [start])])
    vis = {start}
    while q:
        (x, y), path = q.popleft()
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE and (nx, ny) not in vis:
                if (nx, ny) in obs_set:
                    continue
                np = path + [(nx, ny)]
                if (nx, ny) == goal:
                    return np
                vis.add((nx, ny))
                q.append(((nx, ny), np))
    return None


def dir_between(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return {(0, -1): "arriba", (0, 1): "abajo", (-1, 0): "izquierda", (1, 0): "derecha"}.get((dx, dy))


def nearest_plant_with_food(fx, fy):
    best, best_dist = None, 999
    for fd in FOOD:
        if fd["ground"] and fd["on_plant"]:
            d = abs(fd["x"] - fx) + abs(fd["y"] - fy)
            if d < best_dist:
                best_dist = d
                best = (fd["x"], fd["y"])
    return best


def crear_porcion(px, py):
    return {"x": px, "y": 0, "target_y": py, "fall": 0, "ground": False, "on_plant": False}


def agregar_porciones(cantidad=3):
    for _ in range(cantidad):
        px, py = random.choice(GRID["plants"])
        FOOD.append(crear_porcion(px, py))


def crear_snapshot():
    return {"agua": STATE, "pez": FISH, "grid": GRID, "food": FOOD}


def avanzar_reloj(s):
    s["sim_minute"] += 10
    if s["sim_minute"] >= 60:
        s["sim_minute"] = 0
        s["sim_hour"] = (s["sim_hour"] + 1) % 24


def actualizar_temperatura(s):
    hora_dec = s["sim_hour"] + s["sim_minute"] / 60.0
    s["outdoor_temp"] = round(25 + 7 * math.sin((hora_dec - 5) * math.pi / 12), 1)

    drift = (s["outdoor_temp"] - s["temp"]) * 0.03
    if s["heater_on"]:
        diff = s["heater_temp"] - s["temp"]
        drift += clamp(diff * 0.12, -0.4, 0.4)
    s["temp"] = round(clamp(s["temp"] + drift, 15.0, 35.0), 1)


def aplicar_auto_cuidado():
    """Restaura las condiciones ideales mientras el modo automatico esta activo."""
    s, f = STATE, FISH

    s["filter_on"] = True
    s["heater_on"] = True
    s["heater_temp"] = AUTO_CARE_TARGETS["temp"]
    for key, value in AUTO_CARE_TARGETS.items():
        s[key] = value

    hora = s["sim_hour"]
    if 22 <= hora or hora < 6:
        s["light_on"] = False
    else:
        s["light_on"] = True

    if tick_count[0] % 10 == 0:
        hay_comida = any(fd["ground"] for fd in FOOD)
        if f["hunger"] > 40 and not hay_comida:
            agregar_porciones()
            s["last_action"] = f"Auto: alimentar (hambre {f['hunger']}%)"

    s["last_action"] = "Auto: condiciones ideales mantenidas"


def tick_simulation():
    with lock:
        if not FISH["alive"]:
            return

        s, f = STATE, FISH
        tick_count[0] += 1

        avanzar_reloj(s)
        actualizar_temperatura(s)

        f["hunger"] = round(min(100, f["hunger"] + 0.15), 1)

        waste = 0.12 if f["hunger"] < 80 else 0.18
        s["ammonia"] = round(min(5.0, s["ammonia"] + waste), 2)

        if s["filter_on"]:
            s["ammonia"] = round(max(0, s["ammonia"] - 0.15), 2)
            s["nitrite"] = round(max(0, s["nitrite"] - 0.08), 2)
            s["nitrate"] = round(min(100, s["nitrate"] + 0.05), 1)
            s["clarity"] = round(min(100, s["clarity"] + 0.3), 1)
        else:
            s["clarity"] = round(max(0, s["clarity"] - 0.2), 1)

        if s["ammonia"] > 0.5:
            s["nitrite"] = round(min(5.0, s["nitrite"] + 0.06), 2)

        tf = max(0, (s["temp"] - 20) / 15)
        s["oxygen"] = round(clamp(
            s["oxygen"] - 0.1 - tf * 0.05 + (0.3 if s["filter_on"] else 0) + (0.2 if s["light_on"] else 0.05),
            0, 100), 1)

        s["water_level"] = round(max(0, s["water_level"] - 0.03), 1)

        s["ph"] += (0.01 if s["ammonia"] > 1.0 else -0.005)
        if s["filter_on"]:
            s["ph"] += (7.0 - s["ph"]) * 0.01
        s["ph"] = round(clamp(s["ph"], 5.0, 9.0), 2)

        if s["auto_mode"]:
            aplicar_auto_cuidado()

        stress = 0
        if s["temp"] < 24 or s["temp"] > 30: stress += 1.5
        if s["ph"] < 6.5 or s["ph"] > 8.0: stress += 1.0
        if s["ammonia"] > 1.0: stress += 2.0
        if s["nitrite"] > 1.0: stress += 1.5
        if s["nitrate"] > 20.0: stress += 1.0
        if s["oxygen"] < 60: stress += 2.0
        if s["clarity"] < 80.0: stress += 0.5
        if s["water_level"] < 80.0: stress += 0.5
        if f["hunger"] > 80: stress += 1.0
        if not s["light_on"]: stress += 0.3
        f["stress"] = round(clamp(f["stress"] * 0.85 + stress * 0.15, 0, 100), 1)

        hl = 0
        if f["hunger"] > 90: hl += 0.5
        if f["stress"] > 50: hl += 0.3
        if s["ammonia"] > 2.0: hl += 1.0
        if s["oxygen"] < 40: hl += 1.5
        hg = 0.1 if f["stress"] < 20 and f["hunger"] < 50 else 0
        f["health"] = round(clamp(f["health"] - hl + hg, 0, 100), 1)

        if f["health"] <= 0:
            f["alive"] = False
            s["last_action"] = "El pez ha muerto"
            return

        # --- Alimento en plantas ---
        new_food = []
        for fd in FOOD:
            if fd["ground"]:
                if fd["x"] == f["x"] and fd["y"] == f["y"]:
                    f["hunger"] = round(max(0, f["hunger"] - 12), 1)
                    s["ammonia"] = round(min(5.0, s["ammonia"] + 0.08), 2)
                    s["last_action"] = f"Pez comio en planta ({fd['x']},{fd['y']})"
                    continue
                new_food.append(fd)
            else:
                fd["fall"] += 1
                plant_y = fd["target_y"]
                if fd["fall"] >= plant_y:
                    fd["y"] = plant_y
                    fd["ground"] = True
                    fd["on_plant"] = True
                new_food.append(fd)
        FOOD.clear()
        FOOD.extend(new_food)

        # --- Movimiento del pez ---
        target = nearest_plant_with_food(f["x"], f["y"])

        moved = False
        if f["hunger"] > 20 and target:
            tx, ty = target
            dx, dy = tx - f["x"], ty - f["y"]
            if abs(dx) + abs(dy) == 1:
                f["x"], f["y"] = tx, ty
                s["last_action"] = f"Pez llego a planta ({tx},{ty})"
                moved = True
            else:
                path = bfs((f["x"], f["y"]), target)
                if path and len(path) > 1:
                    d = dir_between(path[0], path[1])
                    if d:
                        f["x"], f["y"] = path[1]
                        s["last_action"] = f"Pez va a planta -> {d}"
                        moved = True

        if not moved and tick_count[0] % 4 == 0:
            wc = GRID["plants"][:]
            random.shuffle(wc)
            for dest in wc:
                if dest != (f["x"], f["y"]):
                    path = bfs((f["x"], f["y"]), dest)
                    if path and len(path) > 1:
                        d = dir_between(path[0], path[1])
                        if d:
                            f["x"], f["y"] = path[1]
                            s["last_action"] = f"Pez nadando -> {d}"
                            break


obs_set = set(GRID["heater"] + GRID["filter"] + GRID["rocks"])


def _initial_tick():
    time.sleep(1)
    tick_simulation()

threading.Thread(target=_initial_tick, daemon=True).start()


@mcp.resource("pecera://estado")
def recurso_estado() -> str:
    """Retorna el estado completo de la pecera."""
    with lock:
        return json.dumps(crear_snapshot(), ensure_ascii=False)


@mcp.tool()
def leer_sensores() -> dict:
    """Lee sensores: temperatura, pH, oxigeno, nivel de agua, claridad, estado del pez."""
    with lock:
        return {
            "temperatura": f"{STATE['temp']}°C", "ph": STATE["ph"],
            "oxigeno_disuelto": f"{STATE['oxygen']}%", "nivel_agua": f"{STATE['water_level']}%",
            "claridad": f"{STATE['clarity']}%",
            "pez": {"posicion": (FISH["x"], FISH["y"]), "hambre": f"{FISH['hunger']}%",
                    "estres": f"{FISH['stress']}%", "salud": f"{FISH['health']}%", "vivo": FISH["alive"]},
        }


@mcp.tool()
def alimentar() -> str:
    """Alimenta al pez. Suelta 3 porciones sobre las plantas (pasto)."""
    with lock:
        if not FISH["alive"]:
            return "El pez esta muerto."
        agregar_porciones()
        STATE["last_action"] = "Alimento lanzado sobre el pasto"
        return f"3 porciones cayendo hacia las plantas. Hambre: {FISH['hunger']}%"


@mcp.tool()
def cambiar_temperatura(objetivo: float) -> str:
    """Ajusta el calentador a una temperatura objetivo (24-30°C)."""
    with lock:
        if objetivo < 24 or objetivo > 30:
            return "Error: rango valido 24-30°C."
        STATE["heater_temp"] = objetivo
        STATE["heater_on"] = True
        STATE["last_action"] = f"Calentador a {objetivo}°C"
        return f"Calentador a {objetivo}°C. Actual: {STATE['temp']}°C"


@mcp.tool()
def encender_apagar_luz(encender: bool) -> str:
    """Enciende o apaga la iluminacion."""
    with lock:
        STATE["light_on"] = encender
        STATE["last_action"] = f"Luz {'encendida' if encender else 'apagada'}"
        return f"Luz {'encendida' if encender else 'apagada'}."


@mcp.tool()
def limpiar_filtro() -> str:
    """Limpia el filtro mecanico."""
    with lock:
        if not STATE["filter_on"]:
            return "El filtro esta apagado."
        STATE["ammonia"] = round(max(0, STATE["ammonia"] - 0.5), 2)
        STATE["nitrite"] = round(max(0, STATE["nitrite"] - 0.3), 2)
        STATE["clarity"] = round(min(100, STATE["clarity"] + 15), 1)
        STATE["last_action"] = "Filtro limpiado"
        return f"Filtro limpiado. NH3: {STATE['ammonia']}ppm, Claridad: {STATE['clarity']}%"


@mcp.tool()
def cambiar_agua(porcentaje: float) -> str:
    """Reemplaza un porcentaje del agua (10-50%)."""
    with lock:
        if porcentaje < 10 or porcentaje > 50:
            return "Error: rango valido 10-50%."
        f = porcentaje / 100
        STATE["ammonia"] = round(STATE["ammonia"] * (1 - f * 0.7), 2)
        STATE["nitrite"] = round(STATE["nitrite"] * (1 - f * 0.7), 2)
        STATE["nitrate"] = round(STATE["nitrate"] * (1 - f * 0.5), 1)
        STATE["ph"] = round(STATE["ph"] + (7.2 - STATE["ph"]) * f * 0.5, 2)
        STATE["oxygen"] = round(min(100, STATE["oxygen"] + f * 10), 1)
        STATE["clarity"] = round(min(100, STATE["clarity"] + f * 20), 1)
        STATE["water_level"] = round(min(100, STATE["water_level"] + porcentaje * 0.5), 1)
        STATE["last_action"] = f"Cambio de agua {porcentaje}%"
        return f"Agua cambiada {porcentaje}%."


@mcp.tool()
def verificar_salud_peces() -> dict:
    """Evalua salud del pez segun condiciones del agua."""
    with lock:
        s, f = STATE, FISH
        p = []
        if f["hunger"] > 80: p.append("Hambre alta")
        if f["stress"] > 50: p.append("Estres elevado")
        if s["temp"] < 24 or s["temp"] > 30: p.append("Temperatura fuera de rango")
        if s["ammonia"] > 1.0: p.append("Amoniaco alto")
        if s["nitrite"] > 1.0: p.append("Nitritos altos")
        if s["nitrate"] > 20.0: p.append("Nitratos altos")
        if s["oxygen"] < 60: p.append("Oxigeno bajo")
        if s["clarity"] < 80.0: p.append("Agua turbia")
        if s["water_level"] < 80.0: p.append("Nivel de agua bajo")
        if s["ph"] < 6.5 or s["ph"] > 8.0: p.append("pH fuera de rango")
        est = "Saludable" if f["health"] >= 60 else ("Critico" if f["health"] < 30 else "Debil")
        return {"salud": f"{f['health']}%", "estado": est, "problemas": p or ["Ninguno"], "vivo": f["alive"]}


@mcp.tool()
def activar_desactivar_filtro(activar: bool) -> str:
    """Enciende o apaga el filtro."""
    with lock:
        STATE["filter_on"] = activar
        STATE["last_action"] = f"Filtro {'activado' if activar else 'desactivado'}"
        return f"Filtro {'activado' if activar else 'desactivado'}."


@mcp.tool()
def medir_calidad_agua() -> dict:
    """Mide amonico, nitritos, nitratos y pH."""
    with lock:
        s = STATE
        return {"ammonia_ppm": s["ammonia"], "nitrite_ppm": s["nitrite"],
                "nitrate_ppm": s["nitrate"], "ph": s["ph"], "oxigeno": f"{s['oxygen']}%"}


@mcp.tool()
def agregar_tratamiento(tipo: str) -> str:
    """Agrega tratamiento. Tipos: 'acondicionador', 'medicamento', 'bacteria'."""
    with lock:
        t = tipo.strip().lower()
        cfg = {
            "acondicionador": {"ammonia": -0.4, "nitrite": -0.2, "ph": 0.05, "desc": "Acondicionador"},
            "medicamento": {"health": 15, "stress": -10, "ammonia": 0.1, "desc": "Medicamento"},
            "bacteria": {"ammonia": -0.6, "nitrite": -0.5, "nitrate": 5, "desc": "Bacteria ciclante"},
        }
        if t not in cfg:
            return f"Tipos validos: {', '.join(cfg.keys())}"
        c = cfg[t]
        STATE["ammonia"] = round(clamp(STATE["ammonia"] + c.get("ammonia", 0), 0, 5), 2)
        STATE["nitrite"] = round(clamp(STATE["nitrite"] + c.get("nitrite", 0), 0, 5), 2)
        STATE["nitrate"] = round(clamp(STATE["nitrate"] + c.get("nitrate", 0), 0, 100), 1)
        STATE["ph"] = round(clamp(STATE["ph"] + c.get("ph", 0), 5, 9), 2)
        if "health" in c: FISH["health"] = round(clamp(FISH["health"] + c["health"], 0, 100), 1)
        if "stress" in c: FISH["stress"] = round(clamp(FISH["stress"] + c["stress"], 0, 100), 1)
        STATE["last_action"] = f"Tratamiento: {c['desc']}"
        return f"{c['desc']} aplicado."


@mcp.tool()
def activar_auto_cuidar(activar: bool) -> str:
    """Activa o desactiva el modo automatico. Cuando esta ON, el sistema toma decisiones solo."""
    with lock:
        STATE["auto_mode"] = activar
        if activar:
            aplicar_auto_cuidado()
        STATE["last_action"] = f"Auto-cuidador {'activado' if activar else 'desactivado'}"
        return f"Modo automatico {'ON' if activar else 'OFF'}. Ejecuta acciones cada 10 segundos."


@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "fish_monitor.html")


@app.route("/estado")
def consultar_estado():
    with lock:
        resp = jsonify(crear_snapshot())
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


@app.route("/tick", methods=["POST"])
def ejecutar_tick():
    tick_simulation()
    return jsonify({"ok": True})


def ejecutar_web():
    from werkzeug.serving import make_server
    make_server("127.0.0.1", 5001, app).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=ejecutar_web, daemon=True).start()
    print("Monitor: http://127.0.0.1:5001")
    mcp.run()
