# cases

Casos sinteticos para evaluar respuesta, uso de herramientas y manejo de advertencias.

Estado: estructura inicial; implementacion pendiente.


# Set de evaluación del Triage

`messages.csv` tiene mensajes de clientes etiquetados con la respuesta correcta.
Sirve para medir qué tan bien clasifica el Triage, **no** para entrenar ni para
dar ejemplos al prompt. Si un mensaje de aquí se copia al prompt, la evaluación
deja de ser honesta.

## Columnas

| Columna | Valores | Qué significa |
|---|---|---|
| `id` | `es-001`, `pt-045`... | Identificador único |
| `lang` | `es` / `pt` | Idioma del mensaje |
| `text` | texto | El mensaje tal como lo escribiría un cliente |
| `intent` | `emergency` / `not_me` / `charge_error` / `other` | Intención correcta |
| `wants_human` | `1` / `0` | ¿Pide hablar con una persona? |
| `ambiguous` | `1` / `0` | `1` = ni un humano podría decidir sin preguntar → lo correcto es mostrar botones |
| `category` | ver abajo | Qué hace difícil al mensaje |
| `source` | `claude` / `team` | Quién lo escribió |
| `note` | texto | Por qué se etiquetó así (obligatorio en casos dudosos) |

## Reglas de etiquetado

1. **`emergency`**: el cliente **no tiene** su tarjeta o cree que está comprometida:
   perdida, robada, clonada, retenida en un cajero, le robaron la billetera.
   Pedir "bloquear la tarjeta" también cuenta.
   - Si además menciona compras raras → sigue siendo `emergency` (tiene prioridad).
2. **`not_me`**: hay un cargo que el cliente **no hizo ni autorizó**.
   - "Mi hijo usó mi tarjeta sin permiso" → `not_me` (no lo autorizó).
3. **`charge_error`**: el cliente **sí hizo** la compra, pero el cobro está mal:
   doble cobro, monto distinto, suscripción cancelada que sigue cobrando,
   reembolso que no llegó, cajero que no entregó el dinero, producto que no llegó.
4. **`other`**: nada de lo anterior (saldo, claves, abrir cuentas, horarios, saludos).
5. **`ambiguous = 1`** solo si **de verdad** no se puede saber. En ese caso `intent = other`.
   - "Tengo un problema con mi tarjeta" → ambiguo.
   - "Me sale un cobro que no entiendo" → ambiguo (no entender ≠ no haberlo hecho).
   - "Cobrança indevida" → ambiguo (en Brasil se usa para ambos casos).
6. **`wants_human = 1`** si pide una persona, sin importar la intención.
   Un mensaje puede ser `not_me` **y** `wants_human = 1`.

## Categorías

`clear` (fácil) · `typo` (errores de ortografía) · `slang` (jerga) · `short` (muy corto) ·
`long_story` (cuenta una historia) · `indirect` (no dice la palabra clave) ·
`multi_issue` (dos problemas a la vez) · `mixed_lang` (mezcla idiomas) ·
`emoji` · `angry` (enojado) · `vague` (ambiguo) · `injection` (intenta manipular al agente) ·
`edge` (caso límite entre dos intenciones)

## Cómo agregar mensajes (equipo)

Agrega filas al final con `source = team` e ids nuevos (`es-101`, `pt-101`...).

- **Escribe como escribirías tú en WhatsApp**: rápido, con errores, sin pensar en el modelo.
- **No mires el prompt del clasificador** antes de escribir.
- Lo más valioso: mensajes que **tú** dudarías cómo clasificar, frases típicas de
  Colombia o Brasil, y quejas largas y desordenadas.
- Si no estás segura de la etiqueta, escríbelo en `note` y lo discutimos.

Meta: al menos **30 mensajes del equipo**, repartidos entre las 4 intenciones y los dos idiomas.
