---
name: ollama-pecera
description: "Consulta al modelo local de Ollama (qwen35-9b-32k:latest) mediante REST en terminal, como evidencia local del harness, sin archivos ni dependencias propias."
---

## Nombre y Propósito

Comunica al harness con el modelo local de Ollama en http://localhost:11434. Cuando el Conductor asigna un paso a este canal, Tester ejecuta UNA llamada REST por terminal (no se crean ni se usan archivos propios) y devuelve la respuesta cruda del modelo como evidencia local. Útil para pasajes en vivo en los que se requiere que un modelo local (no Copilot) genere o valide contenido.

## Input Schema

```json
{"type": "object", "properties": {"instruccion": {"type": "string", "description": "Instrucción en lenguaje natural para el modelo local"}}, "required": ["instruccion"]}
```

## Flujo de Trabajo

1. Sustituí <instruccion> en el comando por la instrucción recibida (escapada para JSON, en una sola línea), y ejecutalo en terminal:

```
curl.exe -s http://localhost:11434/api/chat -d "{\"model\":\"qwen35-9b-32k:latest\",\"messages\":[{\"role\":\"user\",\"content\":\"<instruccion>\"}],\"stream\":false,\"keep_alive\":\"10m\",\"options\":{\"temperature\":0.1,\"top_p\":0.9,\"seed\":42,\"num_ctx\":8192}}"
```

2. El comando devuelve JSON: respuesta en message.content, telemetría en eval_count/eval_duration; incluí ambos en el reporte.
3. Si Ollama no responde (conexión rechazada o JSON de error), reportalo sin reintentos y escala al Conductor; verificá con `ollama list` que el tag exista exacto.
4. No se crean, modifican ni eliminan archivos; no se instala nada; no se usan las tools MCP de Copilot en este paso.

## Output Schema

```json
{"comando": "<curl ejecutado>", "exit_code": 0, "modelo": "qwen35-9b-32k:latest", "respuesta": "<message.content>", "telemetria": {"eval_count": 0, "eval_duration": 0}}
```

## Restricciones

- Solo esa única llamada REST; sin reintentos automáticos; sin archivos temporales.
- Si exit_code != 0, entregar la salida cruda y un diagnóstico breve sin inventar resultados.

## Criterio de Éxito

exit_code == 0 y message.content no vacío, con la línea de telemetría presente en el reporte.
