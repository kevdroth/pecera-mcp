import copy
import importlib.util
import json
import threading
from pathlib import Path

import pytest


@pytest.fixture
def tank(monkeypatch):
    # Arrange: impedir el hilo de importación para aislar el estado del módulo.
    class NoOpThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(threading, "Thread", NoOpThread)
    path = Path(__file__).parents[1] / "mcp" / "fish_tank_server.py"
    spec = importlib.util.spec_from_file_location("fish_tank_server_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    saved_state = copy.deepcopy(module.STATE)
    saved_fish = copy.deepcopy(module.FISH)
    saved_food = copy.deepcopy(module.FOOD)
    saved_ticks = module.tick_count[0]
    yield module

    # Assert de aislamiento: restaurar todos los globales mutables del dominio.
    module.STATE.clear()
    module.STATE.update(saved_state)
    module.FISH.clear()
    module.FISH.update(saved_fish)
    module.FOOD.clear()
    module.FOOD.extend(saved_food)
    module.tick_count[0] = saved_ticks


def test_clamp_bfs_and_direction_cover_normal_edges_and_obstacle(tank):
    # Arrange
    tank.obs_set = {(1, 0)}

    # Act
    clamped_low = tank.clamp(-1, 0, 10)
    clamped_high = tank.clamp(11, 0, 10)
    path = tank.bfs((0, 0), (2, 0))
    same_path = tank.bfs((2, 2), (2, 2))
    direction = tank.dir_between((0, 0), (1, 0))

    # Assert
    assert clamped_low == 0
    assert clamped_high == 10
    assert path == [(0, 0), (0, 1), (1, 1), (2, 1), (2, 0)]
    assert same_path == []
    assert direction == "derecha"
    assert tank.dir_between((0, 0), (2, 0)) is None


def test_food_helpers_select_nearest_and_create_falling_portion(tank):
    # Arrange
    tank.FOOD.extend([
        {"x": 4, "y": 4, "ground": True, "on_plant": True},
        {"x": 1, "y": 3, "ground": True, "on_plant": True},
        {"x": 0, "y": 0, "ground": False, "on_plant": False},
    ])

    # Act
    nearest = tank.nearest_plant_with_food(2, 2)
    portion = tank.crear_porcion(3, 4)

    # Assert
    assert nearest == (1, 3)
    assert portion == {
        "x": 3, "y": 0, "target_y": 4, "fall": 0,
        "ground": False, "on_plant": False,
    }


def test_clock_temperature_and_snapshot_update_domain_deterministically(tank):
    # Arrange
    state = copy.deepcopy(tank.STATE)
    state.update(sim_hour=8, sim_minute=55, temp=26.0)

    # Act
    tank.avanzar_reloj(state)
    tank.actualizar_temperatura(state)
    snapshot = tank.crear_snapshot()

    # Assert
    assert (state["sim_hour"], state["sim_minute"]) == (9, 0)
    assert 15.0 <= state["temp"] <= 35.0
    assert snapshot["agua"] is tank.STATE
    assert snapshot["pez"] is tank.FISH
    assert snapshot["food"] is tank.FOOD


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("cambiar_temperatura", 24, "Calentador a 24°C"),
        ("cambiar_temperatura", 30, "Calentador a 30°C"),
        ("cambiar_agua", 10, "Agua cambiada 10%."),
        ("cambiar_agua", 50, "Agua cambiada 50%."),
    ],
)
def test_tools_accept_valid_boundaries(tank, name, value, expected):
    # Arrange
    function = getattr(tank, name)

    # Act
    result = function(value)

    # Assert
    assert result.startswith(expected)


@pytest.mark.parametrize(
    ("function", "argument"),
    [
        ("cambiar_temperatura", 23.99),
        ("cambiar_temperatura", 30.01),
        ("cambiar_agua", 9.99),
        ("cambiar_agua", 50.01),
    ],
)
def test_tools_reject_invalid_ranges_without_mutation(tank, function, argument):
    # Arrange
    before = copy.deepcopy(tank.STATE)

    # Act
    result = getattr(tank, function)(argument)

    # Assert
    assert result.startswith("Error: rango valido")
    assert tank.STATE == before


def test_water_filter_light_treatment_and_measurement_apply_expected_changes(tank):
    # Arrange
    tank.STATE.update(ammonia=1.0, nitrite=0.5, nitrate=30.0, clarity=70.0)
    tank.FISH.update(health=50.0, stress=20.0)

    # Act
    filter_result = tank.activar_desactivar_filtro(False)
    light_result = tank.encender_apagar_luz(False)
    treatment_result = tank.agregar_tratamiento(" medicamento ")
    measurement = tank.medir_calidad_agua()

    # Assert
    assert filter_result == "Filtro desactivado."
    assert light_result == "Luz apagada."
    assert treatment_result == "Medicamento aplicado."
    assert tank.FISH["health"] == 65.0
    assert tank.FISH["stress"] == 10.0
    assert measurement["ammonia_ppm"] == 1.1
    assert measurement["oxigeno"] == "85.0%"


def test_tools_handle_dead_fish_disabled_filter_and_unknown_treatment(tank, monkeypatch):
    # Arrange
    tank.FISH["alive"] = False
    tank.STATE["filter_on"] = False
    monkeypatch.setattr(tank.random, "choice", lambda plants: plants[0])

    # Act
    feed_result = tank.alimentar()
    clean_result = tank.limpiar_filtro()
    treatment_result = tank.agregar_tratamiento("desconocido")

    # Assert
    assert feed_result == "El pez esta muerto."
    assert clean_result == "El filtro esta apagado."
    assert treatment_result == "Tipos validos: acondicionador, medicamento, bacteria"
    assert tank.FOOD == []


def test_alimentar_adds_three_deterministic_portions(tank, monkeypatch):
    # Arrange
    monkeypatch.setattr(tank.random, "choice", lambda plants: plants[0])

    # Act
    result = tank.alimentar()

    # Assert
    assert result == "3 porciones cayendo hacia las plantas. Hambre: 20%"
    assert len(tank.FOOD) == 3
    assert all(food["x"] == 1 and food["target_y"] == 4 for food in tank.FOOD)


def test_auto_care_restores_targets_and_respects_night_light(tank):
    # Arrange
    tank.STATE.update(sim_hour=23, temp=20, ammonia=3, auto_mode=True, light_on=True)
    tank.FISH["hunger"] = 20
    tank.tick_count[0] = 1

    # Act
    tank.aplicar_auto_cuidado()

    # Assert
    for key, value in tank.AUTO_CARE_TARGETS.items():
        assert tank.STATE[key] == value
    assert tank.STATE["filter_on"] is True
    assert tank.STATE["heater_on"] is True
    assert tank.STATE["light_on"] is False
    assert tank.STATE["last_action"] == "Auto: condiciones ideales mantenidas"


def test_tick_updates_state_and_dead_fish_is_unchanged(tank, monkeypatch):
    # Arrange
    monkeypatch.setattr(tank.random, "shuffle", lambda values: None)
    starting_tick = tank.tick_count[0]
    initial_hunger = tank.FISH["hunger"]

    # Act
    tank.tick_simulation()

    # Assert
    assert tank.tick_count[0] == starting_tick + 1
    assert tank.FISH["hunger"] == round(initial_hunger + 0.15, 1)
    assert tank.STATE["water_level"] == 100.0

    # Arrange
    tank.FISH["alive"] = False
    before = (copy.deepcopy(tank.STATE), copy.deepcopy(tank.FISH), list(tank.FOOD))
    dead_tick = tank.tick_count[0]

    # Act
    tank.tick_simulation()

    # Assert
    assert (tank.STATE, tank.FISH, tank.FOOD) == before
    assert tank.tick_count[0] == dead_tick


def test_health_report_returns_healthy_and_critical_classifications(tank):
    # Arrange
    tank.FISH.update(health=80, hunger=20, stress=5)

    # Act
    healthy = tank.verificar_salud_peces()

    # Assert
    assert healthy == {
        "salud": "80%",
        "estado": "Saludable",
        "problemas": ["Ninguno"],
        "vivo": True,
    }

    # Arrange
    tank.FISH.update(health=20, hunger=90, stress=60)
    tank.STATE.update(temp=32, ammonia=2, nitrite=2, nitrate=30, oxygen=50,
                      clarity=70, water_level=70, ph=8.5)

    # Act
    critical = tank.verificar_salud_peces()

    # Assert
    assert critical["estado"] == "Critico"
    assert critical["vivo"] is True
    assert len(critical["problemas"]) == 10


def test_flask_routes_return_contracts_and_json(tank, monkeypatch):
    # Arrange
    monkeypatch.setattr(tank.random, "shuffle", lambda values: None)
    client = tank.app.test_client()
    starting_tick = tank.tick_count[0]

    # Act
    tick_response = client.post("/tick")
    state_response = client.get("/estado")
    index_response = client.get("/")

    # Assert
    assert tick_response.status_code == 200
    assert tick_response.get_json() == {"ok": True}
    assert state_response.status_code == 200
    assert state_response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert set(state_response.get_json()) == {"agua", "pez", "grid", "food"}
    assert tank.tick_count[0] == starting_tick + 1
    assert index_response.status_code == 200
    assert "text/html" in index_response.content_type


def test_resource_state_is_valid_json_and_sensor_contract_is_strict(tank):
    # Arrange
    tank.STATE["temp"] = 27.5

    # Act
    resource = json.loads(tank.recurso_estado())
    sensors = tank.leer_sensores()

    # Assert
    assert set(resource) == {"agua", "pez", "grid", "food"}
    assert resource["agua"]["temp"] == 27.5
    assert sensors["temperatura"] == "27.5°C"
    assert sensors["pez"]["posicion"] == (2, 2)
    assert set(sensors) == {
        "temperatura", "ph", "oxigeno_disuelto", "nivel_agua", "claridad", "pez",
    }
