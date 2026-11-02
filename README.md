# Pecera MCP

Simulador de una pecera controlable mediante herramientas MCP, con un monitor
web local y un puente opcional hacia Ollama. El sistema modela la calidad del
agua, el estado del pez, el alimento, los equipos y la evolución temporal de
la pecera.

## Características

- Simulación en memoria de agua, pez, alimento, plantas, rocas, calentador y
  filtro.
- Recurso MCP `pecera://estado` para consultar el estado completo.
- Herramientas MCP para sensores, alimentación, temperatura, iluminación,
  filtro, cambios de agua, tratamientos, salud y modo automático.
- Monitor web servido por Flask en `http://127.0.0.1:5001`.
- Puente MCP opcional para interpretar instrucciones con Ollama y ejecutar
  como máximo una acción validada.
- Pruebas automatizadas con pytest para la simulación y el puente.

## Estructura

```text
pecera/
├── mcp/
│   ├── fish_tank_server.py   # Servidor MCP, simulación y API HTTP
│   ├── fish_monitor.html     # Monitor visual en el navegador
│   └── ollama_bridge.py      # Puente MCP hacia Ollama
├── tests/
│   ├── test_fish_tank_server.py
│   └── test_ollama_bridge.py
├── docs/
│   ├── arquitectura.md
│   ├── flujo-de-datos.md
│   └── auditoria-seguridad.md
└── .vscode/
    └── mcp.json              # Registro del puente para VS Code
```

## Requisitos

- Python 3.10 o superior.
- Dependencias de Python compatibles con los imports del proyecto:
  `flask`, `pytest` y el SDK que proporciona `mcp.server.mcpserver`.
- Ollama local únicamente si se utilizará el puente de lenguaje.
- Modelo `qwen35-9b-32k:latest` disponible en Ollama para usar el puente.

El repositorio no incluye actualmente un archivo `requirements.txt` ni un
lockfile. Por ello, las versiones de las dependencias deben gestionarse en el
entorno donde se ejecute la aplicación.

## Ejecución del servidor y monitor

Desde la raíz del proyecto:

```powershell
python -u mcp\fish_tank_server.py
```

El servidor MCP utiliza `stdio`. En paralelo, inicia el monitor web en
`http://127.0.0.1:5001`. Abre esa dirección en el navegador para visualizar la
pecera.

El monitor consulta `GET /estado` cada 300 ms y solicita un avance de
simulación mediante `POST /tick` cada segundo. El estado no se persiste en
archivos ni en una base de datos; se pierde al detener el proceso.

### API HTTP del monitor

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/` | Sirve el monitor HTML. |
| `GET` | `/estado` | Devuelve el snapshot de agua, pez, cuadrícula y alimento. |
| `POST` | `/tick` | Ejecuta un ciclo de simulación. |

La API web está enlazada a `127.0.0.1:5001` y no implementa autenticación.
Debe mantenerse en loopback salvo que se agreguen controles de acceso
adecuados.

## Herramientas MCP

El servidor principal expone:

- `leer_sensores`
- `alimentar`
- `cambiar_temperatura`
- `encender_apagar_luz`
- `limpiar_filtro`
- `cambiar_agua`
- `verificar_salud_peces`
- `activar_desactivar_filtro`
- `medir_calidad_agua`
- `agregar_tratamiento`
- `activar_auto_cuidar`

Los rangos principales son una temperatura objetivo de 24 a 30 °C y cambios de
agua de 10 a 50 %. Los tipos de tratamiento admitidos son `acondicionador`,
`medicamento` y `bacteria`.

## Uso con Ollama

El puente se ejecuta como un servidor MCP independiente:

```powershell
python -u mcp\ollama_bridge.py
```

La configuración de VS Code ya está registrada en
[.vscode/mcp.json](.vscode/mcp.json). El puente consulta por defecto:

```text
http://localhost:11434/api/chat
```

Variables de entorno disponibles:

| Variable | Valor predeterminado | Descripción |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Proveedor habilitado por el puente. |
| `LLM_BASE_URL` | `http://localhost:11434` | URL base de Ollama. |
| `OLLAMA_TIMEOUT` | `45` segundos | Tiempo máximo de consulta, limitado a 120 segundos. |
| `MCP_READ_TIMEOUT` | `15` segundos | Tiempo máximo de lectura del servidor hijo, limitado a 60 segundos. |

El modelo utilizado está fijado en `qwen35-9b-32k:latest`. El puente valida el
nombre, el tipo, los argumentos y los rangos de cada acción antes de enviarla
al servidor MCP hijo.

## Pruebas

Ejecuta la suite desde la raíz:

```powershell
python -m pytest
```

Las pruebas cubren la lógica de la simulación, los límites de las herramientas,
el aislamiento del estado y la validación del puente sin requerir una conexión
real con Ollama.

## Documentación adicional

- [Arquitectura actual](docs/arquitectura.md)
- [Flujo de datos](docs/flujo-de-datos.md)
- [Auditoría de seguridad](docs/auditoria-seguridad.md)

## Limitaciones conocidas

- El estado es global y vive únicamente en memoria.
- El monitor HTTP no tiene autenticación ni autorización.
- El puente no establece actualmente un límite de longitud para la instrucción
  antes de enviarla a Ollama.
- No hay un manifiesto versionado de dependencias, por lo que la instalación
  no es completamente reproducible.
