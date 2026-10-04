# tools

Definiciones de herramientas MCP y validacion de argumentos (`server.py`).

`verify_identity` emite un token de sesion firmado; los demas tools reciben ese
token y obtienen `customer_id` de el, nunca de un argumento. Ver ../../README.md.
