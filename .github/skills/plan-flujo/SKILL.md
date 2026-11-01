---
name: plan-flujo
description: "Convierte un objetivo y sus restricciones en un pipeline JSON verificable de agentes, skills y criterios de éxito para el harness de la pecera."
---

## Nombre y Propósito

Planificar la ejecución multiagente. Esta skill la invoca el Orquestador para transformar un objetivo de ingeniería en un pipeline ordenado de contexto, tarea y validación, con un agente responsable, una skill concreta y un criterio de éxito comprobable en cada paso.

No ejecuta el plan: solo lo diseña y lo devuelve en JSON para que el Orquestador lo delegue.

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "objetivo": {
      "type": "string",
      "description": "Resultado de ingeniería esperado, expresado como una acción verificable."
    },
    "restricciones": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Límites del usuario: archivos permitidos, dimensiones, prohibiciones y criterios de aceptación."
    },
    "contexto_repo": {
      "type": "string",
      "description": "Rutas, hallazgos o resumen del repositorio disponibles antes de planificar."
    },
    "dimensiones": {
      "type": "array",
      "items": {
        "enum": [
          "documentacion",
          "pruebas",
          "seguridad"
        ]
      },
      "description": "Dimensiones complementarias que debe cubrir el plan."
    },
    "max_pasos": {
      "type": "integer",
      "minimum": 2,
      "maximum": 8,
      "default": 6
    }
  },
  "required": [
    "objetivo",
    "restricciones"
  ],
  "additionalProperties": false
}
```

## Workflow interno

1. Normalizar el objetivo en una frase verificable y listar las restricciones que limitan archivos, herramientas o alcance.
2. Identificar las dimensiones solicitadas. Si el usuario no especifica ninguna, asumir documentación o pruebas según la naturaleza del objetivo y declararlo en `supuestos`.
3. Construir el pipeline base en este orden: contexto (`generar-contexto`), tarea (`retroalimentar-doc`, `generar-pruebas-aaa` o `auditar-seguridad`) y validación (Tester).
4. Asignar cada paso a un agente existente del catálogo y a una skill existente. No crear agentes ni skills nuevas.
5. Redactar un criterio de éxito observable por paso: un diff, un archivo `.md` validado, una salida de pytest con código de salida, un reporte con severidades o una cita `ruta:línea`.
6. Insertar dependencias explícitas cuando un paso necesite el artefacto del anterior y verificar que el plan no supere `max_pasos`.
7. Agregar un criterio de aprobación global y un máximo de iteraciones del bucle de retroalimentación.
8. Devolver solo el JSON de salida. No ejecutar ninguna skill, no leer archivos y no escribir en disco.

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "objetivo": {
      "type": "string"
    },
    "supuestos": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "pipeline": {
      "type": "object",
      "properties": {
        "pasos": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "agente": {
                "enum": [
                  "Orquestador",
                  "Context-Builder",
                  "Tester"
                ]
              },
              "skill": {
                "type": "string"
              },
              "criterio_exito": {
                "type": "string"
              }
            },
            "required": [
              "agente",
              "skill",
              "criterio_exito"
            ]
          }
        },
        "criterio_aprobacion_global": {
          "type": "string"
        },
        "max_iteraciones": {
          "type": "integer"
        }
      },
      "required": [
        "pasos",
        "criterio_aprobacion_global",
        "max_iteraciones"
      ]
    }
  },
  "required": [
    "objetivo",
    "supuestos",
    "pipeline"
  ]
}
```

## Restricciones

- No invoca agentes ni ejecuta skills; solo planifica.
- No lee archivos, no usa terminal, no escribe archivos y no hace `commit`.
- No inventa agentes ni skills: el catálogo válido es `Orquestador`, `Context-Builder`, `Tester` y las skills `generar-contexto`, `retroalimentar-doc`, `generar-pruebas-aaa`, `auditar-seguridad`.
- No asigna a `Context-Builder` la escritura de código ni de pruebas; su ámbito es `.md`.
- No asigna a `Tester` la modificación de código de producción; su ámbito son los tests y la auditoría.
- Si el objetivo exige implementar o corregir código de producción, no inventa un implementador: registra la limitación en `supuestos` y recomienda aprobación humana.
- Cada paso debe tener un criterio de éxito medible; no se aceptan criterios genéricos como "revisar" o "mejorar".
- El plan no puede superar 8 pasos ni 3 iteraciones de retroalimentación.
- La salida es un único bloque JSON válido, sin texto adicional antes o después.

## Parámetros

```yaml
temperature: 0.2
top_p: 0.9
seed: 42
max_pasos_default: 6
max_iteraciones: 3
```

Justificación: `temperature: 0.2` permite comparar alternativas de descomposición sin dispersar el plan; es más flexible que el 0.1 usado para código, pero sigue siendo determinista. `top_p: 0.9` recorta tokens improbables y mantiene coherencia estructural. `seed: 42` hace reproducible el mismo plan ante las mismas entradas. El límite de 6 pasos evita pipelines inflados y el de 3 iteraciones acota el bucle de retroalimentación.
