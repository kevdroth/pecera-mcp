---
name: retroalimentar-doc
description: "Actualiza un documento Markdown a partir de hallazgos verificados, aplicando un diff mínimo, conservando el contenido válido y validando el formato final."
---

## Nombre y Propósito

Mantener la documentación sincronizada con el código. Esta skill la invoca Context-Builder para leer un `.md`, compararlo con hallazgos verificados, actualizar solo las secciones afectadas y validar que el resultado siga siendo un documento Markdown coherente.

Es la habilidad que cubre la dimensión de documentación del parcial: no reescribe por reescribir, sino que incorpora evidencia nueva con trazabilidad.

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "hallazgos": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "tipo": {
            "type": "string"
          },
          "detalle": {
            "type": "string"
          },
          "evidencia": {
            "type": "string",
            "description": "Referencia ruta:línea o salida de comando que respalda el hallazgo."
          },
          "seccion_sugerida": {
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
    "ruta_destino": {
      "type": "string",
      "pattern": "\\.md$",
      "description": "Ruta del archivo Markdown a actualizar o crear."
    },
    "modo": {
      "enum": [
        "actualizar",
        "crear"
      ],
      "default": "actualizar"
    },
    "restricciones_formato": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Reglas adicionales del documento, por ejemplo jerarquía de encabezados o idioma."
    }
  },
  "required": [
    "hallazgos",
    "ruta_destino"
  ],
  "additionalProperties": false
}
```

## Workflow interno

1. Validar que `ruta_destino` termine en `.md`. Si no, rechazar la operación y explicar que el ámbito de esta skill es exclusivamente Markdown.
2. Leer el archivo destino. Si no existe y `modo` es `actualizar`, detenerse con un error claro; si `modo` es `crear`, construir una estructura mínima con título, propósito, arquitectura, flujo, operación y limitaciones.
3. Normalizar los hallazgos: eliminar duplicados, agrupar por tema y asignar cada uno a una sección existente o a una sección nueva justificada.
4. Calcular el diff lógico contra el contenido actual. Conservar párrafos, ejemplos y enlaces que sigan siendo válidos; no reescribir el documento completo.
5. Actualizar el archivo con `write_file`, aplicando el cambio mínimo. Si el hallazgo contradice una afirmación previa, corregirla y citar la evidencia que lo respalda.
6. Validar el formato: frontmatter si ya existía, jerarquía de encabezados, enlaces, bloques de código balanceados, texto en español, ausencia de emojis y codificación UTF-8 sin BOM.
7. Verificar que no se hayan introducido afirmaciones sin evidencia. Si falta respaldo, mover el texto a una nota de `pendiente` o eliminarlo.
8. Devolver el JSON de salida con el archivo actualizado, las secciones modificadas y el resumen del diff. Si el cliente no puede releer el archivo, incluir `contenido_actualizado`.

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "archivo": {
      "type": "string"
    },
    "modo": {
      "enum": [
        "actualizar",
        "crear"
      ]
    },
    "secciones_modificadas": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "secciones_agregadas": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "resumen_diff": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "validacion": {
      "type": "object",
      "properties": {
        "formato_ok": {
          "type": "boolean"
        },
        "encabezados_ok": {
          "type": "boolean"
        },
        "enlaces_ok": {
          "type": "boolean"
        },
        "sin_emojis": {
          "type": "boolean"
        },
        "observaciones": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": [
        "formato_ok",
        "encabezados_ok",
        "enlaces_ok",
        "sin_emojis",
        "observaciones"
      ]
    },
    "contenido_actualizado": {
      "type": "string"
    }
  },
  "required": [
    "archivo",
    "modo",
    "secciones_modificadas",
    "secciones_agregadas",
    "resumen_diff",
    "validacion"
  ]
}
```

## Restricciones

- Solo escribe archivos `.md`. Nunca modifica `.py`, `.json`, `.html`, `.txt`, tests ni configuración.
- No modifica `README.md` salvo instrucción explícita y por escrito del usuario.
- No usa terminal, no instala dependencias y no hace `commit`.
- No borra secciones completas ni reescribe el documento sin aprobación; el cambio es de diff mínimo.
- No inventa hallazgos, evidencias ni enlaces. Si un dato no está verificado, lo marca como pendiente.
- No incluye secretos, credenciales ni datos sensibles, ni siquiera en ejemplos.
- No introduce emojis ni cambia el idioma del documento sin solicitarlo.
- Si el archivo destino no es `.md`, se detiene y escala; no crea una versión en otro formato.
- La salida es un único JSON válido, en español.

## Parámetros

```yaml
temperature: 0.1
top_p: 0.9
num_ctx: 32768
seed: 42
keep_alive: "10m"
```

Justificación: `temperature: 0.1` mantiene la edición fiel al contenido existente y evita reescrituras creativas. `top_p: 0.9` reduce tokens improbables y conserva la estructura. `seed: 42` hace reproducible la misma actualización ante los mismos hallazgos. `num_ctx: 32768` permite leer el documento completo y compararlo con el mapa del repositorio. `keep_alive: "10m"` evita recargar el modelo entre iteraciones del bucle de documentación.
