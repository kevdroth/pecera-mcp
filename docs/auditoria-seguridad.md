# Auditoría de seguridad

## Alcance

Esta auditoría cubre la revisión estática del servidor MCP, el monitor HTTP y
el puente con Ollama en `mcp/`. Se consideran las superficies `/estado`,
`/tick`, la entrada de instrucciones al puente y la gestión de dependencias.
No se detectaron secretos en la evidencia revisada.

Para el contexto de componentes y responsabilidades, consultar
[Arquitectura actual](arquitectura.md). El flujo de solicitudes y estado se
describe en [Flujo de datos](flujo-de-datos.md).

## Metodología

Se inspeccionaron los puntos de entrada, validaciones y configuración de
escucha/dependencias mediante análisis estático del código y los hallazgos de
auditoría suministrados. Cada observación se contrastó con su ruta y rango de
líneas. No se realizaron pruebas dinámicas, pruebas de penetración ni
verificación de explotación, y las remediaciones indicadas son propuestas,
no cambios aplicados.

## Hallazgos

| ID | Severidad | Categoría | Evidencia | Impacto |
|---|---|---|---|---|
| SEC-001 | Baja | Permisos | `mcp/fish_tank_server.py:434-450` define `/estado` y `POST /tick` sin autenticación, autorización ni protección CSRF. `mcp/fish_tank_server.py:455` crea el servidor con `make_server` y `mcp/fish_tank_server.py:461` mantiene el enlace a `127.0.0.1:5001`. | Un proceso o página con capacidad de solicitar conexiones al host local podría leer el estado y provocar ticks. El enlace de loopback limita la exposición a la máquina local. |
| SEC-002 | Baja | Validación de entradas | `mcp/ollama_bridge.py:326-329` rechaza instrucciones vacías; el flujo posterior de envío y procesamiento se encuentra en `mcp/ollama_bridge.py:330-358` y no establece un límite de longitud en caracteres o bytes antes de enviarlas a Ollama. | Una instrucción excesivamente grande podría aumentar el consumo de memoria, procesamiento o tiempo de respuesta y contribuir a una denegación de servicio. |
| SEC-003 | Baja | Dependencias | Los imports del servidor aparecen en `mcp/fish_tank_server.py:11-12` y los imports usados por el puente aparecen en `mcp/ollama_bridge.py:9-10`; la comunicación con Ollama se realiza en `mcp/ollama_bridge.py:281-289`. No existe un manifiesto versionado de dependencias en la raíz ni en el inventario revisado. | Las instalaciones no son reproducibles y el análisis fiable de vulnerabilidades CVE de dependencias queda limitado. |

## Remediaciones concretas propuestas

### SEC-001

- Mantener el enlace a `127.0.0.1` como defensa de exposición de red.
- Añadir autenticación local o un token CSRF aleatorio para `POST /tick`.
- Complementar esa defensa con validación de `Origin` o `Referer`, sin tratar
  esos encabezados como único mecanismo de autorización.
- Evaluar también el control de acceso de `/estado` según el modelo de uso
  local del monitor.

### SEC-002

- Establecer un límite explícito de caracteres o bytes para `instruccion`
  antes de llamar a Ollama.
- Rechazar de forma controlada las entradas que excedan el límite, con un
  mensaje de error no sensible y sin iniciar la solicitud al proveedor.
- Elegir y documentar el límite conforme a los recursos y al modelo
  configurado.

### SEC-003

- Añadir un manifiesto versionado de dependencias.
- Fijar versiones controladas, idealmente mediante un lockfile compatible con
  el mecanismo de instalación adoptado.
- Incorporar el manifiesto al proceso de instalación y al escaneo de
  vulnerabilidades para permitir resultados reproducibles.

## Recomendaciones generales

1. Revalidar periódicamente las rutas HTTP y cualquier nueva superficie de
   entrada con revisión estática y pruebas dinámicas autorizadas.
2. Mantener el servicio HTTP en loopback salvo que exista una necesidad
   documentada de exposición externa; si se expone, aplicar autenticación,
   autorización y protección contra solicitudes de origen cruzado.
3. Registrar rechazos de validación sin almacenar instrucciones completas ni
   otros datos potencialmente sensibles.
4. Revisar y actualizar las dependencias con versiones fijadas y escaneos
   reproducibles.
5. Documentar los límites operativos del puente, los tiempos de espera y las
   políticas de disponibilidad del proveedor Ollama.

## Limitaciones

- El resultado es una auditoría estática acotada a los archivos y rangos
  indicados; no demuestra la ausencia de otras vulnerabilidades.
- No se ejecutaron el servidor, el monitor, Ollama ni solicitudes HTTP.
- No se verificaron dinámicamente encabezados, control de acceso, consumo de
  recursos, configuración del entorno ni versiones instaladas.
- No se aplicó ninguna de las remediaciones propuestas.
