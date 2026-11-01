---
name: generar-contexto
description: "Lee archivos o directorios del repositorio y devuelve un mapa estructurado, verificable y resumido del código, el estado y las herramientas MCP de la pecera."
---

## Nombre y Propósito

Construir contexto técnico confiable. Esta skill la invoca Context-Builder para inventariar archivos, identificar responsabilidades, trazar el flujo de datos y localizar las herramientas MCP, con evidencia `ruta:línea` y una separación explícita entre hechos verificados y supuestos.

El resultado alimenta la documentación y la planificación; no modifica el repositorio.

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "rutas": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "description": "Archivos o directorios relativos a la raíz del proyecto."
    },
    "directorio": {
      "type": "string",
      "description": "Directorio raíz opcional para resolver las rutas; por defecto, la raíz del workspace."
    },
    "profundidad": {
      "type": "integer",
      "minimum": 1,
      "maximum": 4,
      "default": 2,
      "description": "Niveles de recursión al recorrer directorios."
    },
    "objetivo_contexto": {
      "type": "string",
      "description": "Pregunta o foco del análisis, por ejemplo: arquitectura, flujo de estado o herramientas MCP."
    },
    "incluir_dependencias": {
      "type": "boolean",
      "default": true,
      "description": "Si se deben registrar imports y dependencias externas."
    }
  },
  "required": [
    "rutas",
    "objetivo_contexto"
  ],
  "additionalProperties": false
}
```

## Workflow interno

1. Validar que las rutas existan y que estén dentro del workspace. Si una ruta no existe, registrarla en `no_verificado` y continuar con las demás.
2. Recorrer los archivos hasta la profundidad indicada. Para cada archivo, identificar lenguaje, rol, tamaño aproximado, imports y símbolos principales.
3. Leer el código completo cuando el tamaño lo permita. Si un archivo excede el contexto disponible, analizarlo por bloques y declarar qué parte quedó sin leer.
4. Trazar el flujo de datos: entrada, estado, transformación, salida. En la pecera, conectar el tick de simulación, el estado global, las herramientas MCP, el recurso `pecera://estado`, las rutas Flask y el monitor web.
5. Inventariar las herramientas MCP y el recurso expuesto, con nombre, descripción y parámetros observados en el código.
6. Detectar hallazgos relevantes: acoplamiento, estado global mutable, hilos, rutas duplicadas, dependencias no declaradas o riesgos evidentes. Cada hallazgo debe citar `ruta:línea`.
7. Separar supuestos de hechos y listar lo que no se pudo verificar. No completar vacíos con conocimiento genérico.
8. Devolver el JSON de salida. No escribir archivos; si el usuario pide persistir el mapa, derivar a `retroalimentar-doc` con un destino `.md`.

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "resumen": {
      "type": "string"
    },
    "mapa": {
      "type": "object",
      "properties": {
        "raiz": {
          "type": "string"
        },
        "entradas": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "ruta": {
                "type": "string"
              },
              "tipo": {
                "enum": [
                  "archivo",
                  "directorio"
                ]
              },
              "rol": {
                "type": "string"
              },
              "lenguaje": {
                "type": "string"
              },
              "simbolos_clave": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "dependencias": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              },
              "lineas": {
                "type": "integer"
              }
            },
            "required": [
              "ruta",
              "tipo",
              "rol"
            ]
          }
        },
        "flujo_datos": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "herramientas_mcp": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "nombre": {
                "type": "string"
              },
              "descripcion": {
                "type": "string"
              },
              "parametros": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "nombre",
              "descripcion"
            ]
          }
        }
      },
      "required": [
        "raiz",
        "entradas",
        "flujo_datos",
        "herramientas_mcp"
      ]
    },
    "hallazgos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tipo": {
            "enum": [
              "arquitectura",
              "acoplamiento",
              "estado_global",
              "riesgo",
              "otro"
            ]
          },
          "detalle": {
            "type": "string"
          },
          "evidencia": {
            "type": "string"
          }
        },
        "required": [
          "tipo",
          "detalle",
          "evidencia"
        ]
      }
    },
    "supuestos": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "no_verificado": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "resumen",
    "mapa",
    "hallazgos",
    "supuestos",
    "no_verificado"
  ]
}
```

## Restricciones

- Solo lee archivos. No escribe, no renombra y no elimina nada.
- Nunca escribe `.py`; si se pide persistir el contexto, el destino debe ser `.md` y la escritura la realiza `retroalimentar-doc`.
- No usa terminal, no instala dependencias y no hace `commit`.
- No inventa rutas, funciones, herramientas MCP ni líneas. Toda afirmación técnica debe citar evidencia.
- No expone secretos, credenciales ni datos sensibles; si encuentra una credencial, la reporta enmascarada y sin reproducir el valor.
- No analiza archivos fuera del workspace ni sigue enlaces simbólicos que salgan de la raíz.
- Si el contexto no alcanza para leer un archivo completo, lo declara en `no_verificado`; no rellena con suposiciones.
- La salida es un único JSON válido, en español y sin emojis.

## Parámetros

```yaml
temperature: 0.1
top_p: 0.9
num_ctx: 32768
seed: 42
keep_alive: "10m"
```

Justificación: `temperature: 0.1` prioriza fidelidad al código y reduce el riesgo de inventar símbolos o relaciones. `top_p: 0.9` recorta la cola de tokens improbables. `seed: 42` permite reproducir el mismo mapa con las mismas rutas. `num_ctx: 32768` cubre un módulo completo y su documentación sin agotar la ventana; se amplía solo si el archivo lo exige. `keep_alive: "10m"` mantiene el modelo cargado durante la sesión de análisis y evita el arranque en frío.
