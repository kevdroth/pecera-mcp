---
name: auditar-seguridad
description: "Revisa código de forma estática, detecta inyección, validación de entradas, secretos hardcodeados y XSS, clasifica severidad y propone remediaciones verificables."
---

## Nombre y Propósito

Auditar la seguridad del código asignado sin ejecutar explotación. Esta skill la puede invocar Tester o el Orquestador para revisar puntos de entrada, detectar vulnerabilidades comunes, clasificar su severidad y proponer una remediación concreta con evidencia `ruta:línea`.

Cubre la dimensión opcional de seguridad del parcial: detección preventiva, análisis y remediación de riesgos en el servidor MCP y el monitor web de la pecera.

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "objetivo": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "description": "Archivos o directorios a auditar, relativos a la raíz del proyecto."
    },
    "alcance": {
      "type": "array",
      "items": {
        "enum": [
          "inyeccion",
          "validacion_entradas",
          "secretos_hardcodeados",
          "xss",
          "permisos",
          "dependencias"
        ]
      },
      "minItems": 1
    },
    "contexto": {
      "type": "string",
      "description": "Descripción del sistema, la superficie de ataque y las restricciones de la auditoría."
    },
    "profundidad": {
      "enum": [
        "rapida",
        "completa"
      ],
      "default": "rapida"
    }
  },
  "required": [
    "objetivo",
    "alcance"
  ],
  "additionalProperties": false
}
```

## Workflow interno

1. Validar que los objetivos existan y estén dentro del workspace. Registrar las rutas no encontradas y continuar con las demás.
2. Leer el código y enumerar los puntos de entrada: herramientas MCP, recurso MCP, rutas Flask, parámetros de funciones y código JavaScript del monitor.
3. Para cada categoría del alcance, rastrear el dato desde la entrada hasta el sumidero:
   - Inyección: SQL, shell, `eval`, plantillas, rutas de archivo y concatenación de comandos.
   - Validación de entradas: tipos, rangos, enumeraciones, valores límite, `NaN`, cadenas vacías y errores de conversión.
   - Secretos hardcodeados: claves, tokens, contraseñas, cadenas de conexión y valores por defecto inseguros.
   - XSS: `innerHTML`, `outerHTML`, `document.write`, interpolación de plantillas y distinción entre contenido estático y dato controlable.
   - Permisos y dependencias: solo si el alcance lo incluye; revisar exposición de red, modo de depuración y paquetes declarados.
4. Clasificar cada hallazgo con una severidad explícita:
   - Crítica: ejecución remota, secreto expuesto o bypass directo de seguridad.
   - Alta: validación ausente con impacto directo o XSS con dato controlable.
   - Media: defensa en profundidad faltante o error que filtra información.
   - Baja: higiene, cabeceras o mensajes mejorables.
   - Informativa: observación sin explotabilidad demostrada.
5. Proponer una remediación concreta y segura, con el patrón recomendado y la ubicación exacta. No aplicar el cambio.
6. Registrar las limitaciones: revisión estática, sin explotación, sin escaneo de CVE y sin pruebas de carga.
7. Si aparece una vulnerabilidad crítica, marcarla de inmediato y recomendar contención; no intentar explotarla.
8. Devolver el JSON de salida con resumen por severidad, hallazgos, recomendaciones y limitaciones.

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "objetivo": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "alcance_evaluado": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "resumen": {
      "type": "object",
      "properties": {
        "criticos": {
          "type": "integer"
        },
        "altos": {
          "type": "integer"
        },
        "medios": {
          "type": "integer"
        },
        "bajos": {
          "type": "integer"
        },
        "informativos": {
          "type": "integer"
        }
      },
      "required": [
        "criticos",
        "altos",
        "medios",
        "bajos",
        "informativos"
      ]
    },
    "hallazgos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string"
          },
          "categoria": {
            "enum": [
              "inyeccion",
              "validacion_entradas",
              "secretos_hardcodeados",
              "xss",
              "permisos",
              "dependencias"
            ]
          },
          "severidad": {
            "enum": [
              "critica",
              "alta",
              "media",
              "baja",
              "informativa"
            ]
          },
          "ubicacion": {
            "type": "string"
          },
          "evidencia": {
            "type": "string"
          },
          "impacto": {
            "type": "string"
          },
          "remediacion": {
            "type": "string"
          },
          "esfuerzo": {
            "enum": [
              "bajo",
              "medio",
              "alto"
            ]
          }
        },
        "required": [
          "id",
          "categoria",
          "severidad",
          "ubicacion",
          "evidencia",
          "impacto",
          "remediacion",
          "esfuerzo"
        ]
      }
    },
    "recomendaciones_generales": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "limitaciones": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "objetivo",
    "alcance_evaluado",
    "resumen",
    "hallazgos",
    "recomendaciones_generales",
    "limitaciones"
  ]
}
```

## Restricciones

- La auditoría es de solo lectura: no modifica código, configuración ni documentación.
- No ejecuta explotación, pruebas de carga, fuzzing activo ni ataques contra el servidor en ejecución.
- No instala herramientas, no actualiza dependencias y no hace `commit`.
- No reproduce secretos ni credenciales en el reporte; los enmascara y señala su ubicación.
- No audita archivos fuera del ámbito autorizado.
- No declara una vulnerabilidad sin evidencia. Si la explotabilidad no está demostrada, la clasifica como informativa y explica la duda.
- No propone remediaciones genéricas: cada hallazgo debe incluir ubicación, patrón seguro y esfuerzo estimado.
- No aplica las remediaciones; solo las propone para que el usuario o un implementador las aprueben.
- La salida es un único JSON válido, en español y sin emojis.

## Parámetros

```yaml
temperature: 0.1
top_p: 0.9
seed: 42
```

Justificación: `temperature: 0.1` es determinismo estricto para análisis de código: reduce falsos positivos y mantiene la clasificación reproducible. `top_p: 0.9` recorta la cola de tokens improbables y conserva la capacidad de recorrer categorías. `seed: 42` permite repetir la misma auditoría ante el mismo código. La temperatura no se lleva a 0.0 porque el análisis necesita explorar rutas alternativas de datos, pero la evidencia y la severidad se validan contra el código.
