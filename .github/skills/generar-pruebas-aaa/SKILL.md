---
name: generar-pruebas-aaa
description: "Diseña pruebas unitarias con patrón Arrange-Act-Assert para un módulo o clase, escribe archivos test_* y ejecuta pytest para capturar evidencia real."
---

## Nombre y Propósito

Generar y ejecutar pruebas unitarias de calidad sobre el código asignado. Esta skill la invoca Tester para analizar un módulo, diseñar casos típicos, de borde y de excepción, escribir una suite `test_*` con patrón AAA y ejecutar pytest en la terminal para capturar el resultado real.

Cubre la dimensión de pruebas del parcial: aislamiento de funciones, aserciones estrictas y evidencia de ejecución en consola.

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "objetivo": {
      "type": "string",
      "description": "Ruta del módulo o clase a probar, relativa a la raíz del proyecto."
    },
    "simbolos": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Funciones, clases o herramientas MCP que deben cubrirse."
    },
    "ruta_test": {
      "type": "string",
      "pattern": "^tests/test_.*\\.py$",
      "description": "Ruta del archivo de prueba; debe comenzar con tests/ y con test_."
    },
    "framework": {
      "enum": [
        "pytest"
      ],
      "default": "pytest"
    },
    "casos_requeridos": {
      "type": "array",
      "items": {
        "enum": [
          "tipico",
          "borde",
          "excepcion"
        ]
      },
      "minItems": 1
    },
    "restricciones": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Límites adicionales del usuario, por ejemplo no tocar producción o no usar red."
    }
  },
  "required": [
    "objetivo",
    "casos_requeridos"
  ],
  "additionalProperties": false
}
```

## Workflow interno

1. Validar que `objetivo` exista y que `ruta_test`, si se indica, cumpla el patrón `tests/test_*.py`. Si no cumple, corregir la ruta o rechazar la escritura.
2. Leer el módulo y clasificar funciones puras, herramientas MCP, rutas Flask, estado global y efectos secundarios. Identificar qué se puede probar en aislamiento y qué necesita `monkeypatch`, `tmp_path` o mocks.
3. Diseñar los casos requeridos:
   - Típico: entrada válida y resultado esperado.
   - Borde: límites del dominio, listas vacías, valores mínimos o máximos, rutas sin solución.
   - Excepción: entradas inválidas, tipos incorrectos, rangos fuera de contrato o dependencias que fallan.
4. Escribir cada caso con el patrón AAA explícito: Arrange prepara el estado, Act ejecuta una sola acción y Assert verifica con aserciones estrictas. Evitar múltiples acciones en un mismo test.
5. Aislar el estado global de la pecera (`STATE`, `FISH`, `FOOD`, `tick_count`) con fixtures que lo guarden y lo restauren. No depender del hilo de simulación que arranca al importar el módulo, ni de puertos, red o esperas reales.
6. Crear o actualizar el archivo `tests/test_*.py` con nombres descriptivos y datos deterministas. No modificar código de producción.
7. Ejecutar `python -m pytest tests/test_<modulo>.py -v` en la terminal y capturar el código de salida, los conteos de pasados, fallidos y omitidos, y el resumen real.
8. Si hay fallos, clasificarlos: defecto del test o defecto de producción. Corregir solo el test. Si el defecto está en producción, detenerse, documentar la evidencia y devolver `escalar_codigo_produccion`.
9. Devolver el JSON de salida con casos, comando, resultado y siguiente acción.

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "archivo_test": {
      "type": "string"
    },
    "casos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "nombre": {
            "type": "string"
          },
          "tipo": {
            "enum": [
              "tipico",
              "borde",
              "excepcion"
            ]
          },
          "arrange": {
            "type": "string"
          },
          "act": {
            "type": "string"
          },
          "assert": {
            "type": "string"
          }
        },
        "required": [
          "nombre",
          "tipo",
          "arrange",
          "act",
          "assert"
        ]
      }
    },
    "comando": {
      "type": "string"
    },
    "resultado": {
      "type": "object",
      "properties": {
        "exit_code": {
          "type": "integer"
        },
        "pasados": {
          "type": "integer"
        },
        "fallidos": {
          "type": "integer"
        },
        "omitidos": {
          "type": "integer"
        },
        "salida_resumen": {
          "type": "string"
        }
      },
      "required": [
        "exit_code",
        "pasados",
        "fallidos",
        "salida_resumen"
      ]
    },
    "hallazgos": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "siguiente_accion": {
      "enum": [
        "aprobado",
        "corregir_pruebas",
        "escalar_codigo_produccion"
      ]
    }
  },
  "required": [
    "archivo_test",
    "casos",
    "comando",
    "resultado",
    "hallazgos",
    "siguiente_accion"
  ]
}
```

## Restricciones

- Solo escribe archivos `tests/test_*.py`. Nunca modifica código de producción, `README.md`, configuración ni dependencias.
- No instala paquetes ni actualiza el entorno. Si falta `pytest`, `mcp` o `flask`, informa y detente.
- No inicia el servidor MCP ni el monitor web; prueba por importación aislada y mocks.
- No usa red, puertos, `sleep` ni aleatoriedad sin semilla. Los tests deben ser rápidos y deterministas.
- No elimina aserciones, no usa `skip` sin justificación y no oculta fallos.
- No ejecuta comandos destructivos ni cambios de git.
- Toda afirmación de éxito debe incluir el comando ejecutado y el resumen real de pytest.
- Si el defecto está en producción, no lo parchea: escala con evidencia.
- La salida es un único JSON válido, en español y sin emojis.

## Parámetros

```yaml
temperature: 0.1
top_p: 0.9
seed: 42
```

Justificación: `temperature: 0.1` y `seed: 42` son el estándar de determinismo para código de la materia: la misma entrada debe producir la misma suite y el mismo resultado. `top_p: 0.9` recorta la cola de tokens improbables sin impedir que el modelo proponga casos borde. La temperatura no se lleva a 0.0 porque se necesita cierta exploración controlada para imaginar límites; la ejecución real de pytest es la que valida el resultado.
