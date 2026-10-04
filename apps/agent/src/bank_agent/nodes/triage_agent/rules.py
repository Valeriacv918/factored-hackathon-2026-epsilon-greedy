"""Reglas fijas del Triage (código, sin LLM).

Dos usos:
1. REGLAS DE SEGURIDAD que se aplican siempre, digan lo que diga el LLM
   (STATE_MACHINE.md, reglas globales 1 y 2):
   - palabras de robo/pérdida/emergencia  → emergencia de tarjeta
   - pedir una persona         → escalar a humano
2. BASELINE: un clasificador simple de palabras clave. Sirve para comparar:
   si el LLM no le gana al baseline en la evaluación, el LLM no se justifica.
"""
import re
import unicodedata

from bank_agent.nodes.triage_agent.schemas import Intent, Understanding


# ============================================================================
# Utilidades (ya están listas, no hay que cambiarlas)
# ============================================================================

def normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Perdí mi CARTÃO' → 'perdi mi cartao'."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def contains_any(text: str, phrases: list[str]) -> bool:
    """True si el texto contiene alguna frase COMPLETA de la lista.
    \\b = borde de palabra: 'robo' encuentra 'me robo' pero no 'robot'."""
    clean = normalize(text)
    return any(re.search(rf"\b{re.escape(p)}\b", clean) for p in phrases)


# ============================================================================
# TU PARTE 1: las frases
# - Escríbelas en minúsculas y SIN tildes ("perdi", no "Perdí").
# - NO mires evals/triage/messages.csv mientras las escribes.
# - Corre los tests para ver cuáles frases te faltan.
# ============================================================================

EMERGENCY_PHRASES = [
    # espanol
    "me robaron",
    "me clonaron",
    "clonado",
    "perdi mi tarjeta",
    "perdi mi billetera",
    "perdi mi cartera",
    "me robaron la tarjeta",
    "me robaron las tarjetas",
    "me clonaron la tarjeta",
    "me copiaron los datos",
    "me robaron los datos de la tarjeta",
    "me robaron los datos bancarios",
    "me robaron los datos personales",
    "bloquear mi tarjeta",
    "bloquear mi cuenta",
    "bloquear mis cuentas",
    "bloquear mis productos",
    "bloquear todos mis productos",
    "bloqueenme la tarjeta por favor",
    "cuenta comprometida",
    "tarjeta comprometida",
    "mis productos estan comprometidos",
    "me retuvieron la tarjeta",
    "me retuvieron la tarjeta en el cajero",
    "se me quedo la tarjeta en el cajero",
    "el cajero se quedo con mi tarjeta",
    "me robaron el celular",
    "me robaron el celular y tengo la app del banco ahi",
    "perdi el celular y necesito bloquear mis cuentas",
    "me hackearon la cuenta bancaria",
    "me hackearon la banca virtual",
    "me robaron la cuenta del banco",
    "creo que alguien entro a mi cuenta",
    "alguien tiene acceso a mi cuenta",
    "creo que alguien tiene mi clave bancaria",
    "estan intentando entrar a mi cuenta",
    "me estan intentando hackear",
    "me estan intentando robar la cuenta",
    "necesito proteger mi cuenta",
    "necesito asegurar mi cuenta",
    "necesito proteger mis productos bancarios",
    "me bloquearon todos los productos del banco",
    "me bloquearon la cuenta y las tarjetas",
    "necesito bloquear el acceso a mis productos",
    "tengo una emergencia",
    "tengo una emergencia bancaria",
    "tengo una emergencia con mi cuenta",
    "tengo una emergencia con mis tarjetas",
    "tengo una emergencia con mis productos bancarios",
    "tengo un problema urgente de seguridad",
    "necesito ayuda urgente",
    "urgente",
    "me estafaron",
    "me engañaron",
    "me tumbaron",
    "me estan suplantando la identidad",
    "me robaron la identidad",
    "usaron mis datos para pedir un credito",
    "sacaron un credito a mi nombre y yo no fui",
    "hay un prestamo a mi nombre que no solicite",
    "aparecio un credito que nunca pedi",
    "alguien esta intentando sacar un prestamo con mis datos",
    "necesito bloquear una solicitud de credito fraudulenta",
    "estan usando mi identidad para sacar creditos",
    "recibi un codigo de seguridad que no solicite",
    "me llego una alerta de acceso sospechoso",
    "me amenazaron y necesito bloquear mis productos",
    "no puedo entrar a mi cuenta",
    "no puedo acceder a mi cuenta",

    # portugues brasileiro
    "roubaram",
    "clonaram",
    "clonado",
    "perdi meu cartao",
    "perdi meu cartao de credito",
    "perdi meu cartao de debito",
    "perdi minha carteira",
    "roubaram meu cartao",
    "roubaram meus cartoes",
    "copiaram os dados do meu cartao",
    "roubaram os dados do meu cartao",
    "roubaram meus dados bancarios",
    "roubaram meus dados pessoais",
    "preciso bloquear meu cartao",
    "preciso bloquear minha conta",
    "preciso bloquear minhas contas",
    "preciso bloquear meus produtos",
    "bloqueiem meu cartao por favor",
    "minha conta esta comprometida",
    "meu cartao esta comprometido",
    "meus produtos estao comprometidos",
    "reteram meu cartao",
    "o caixa eletronico reteve meu cartao",
    "meu cartao ficou preso no caixa eletronico",
    "roubaram meu celular",
    "roubaram meu celular e o aplicativo do banco esta nele",
    "perdi meu celular e preciso bloquear minhas contas",
    "hackearam minha conta bancaria",
    "invadiram minha conta bancaria",
    "roubaram minha conta bancaria",
    "acho que alguem entrou na minha conta",
    "alguem tem acesso a minha conta",
    "acho que alguem sabe minha senha bancaria",
    "estao tentando acessar minha conta",
    "estao tentando hackear minha conta",
    "estao tentando roubar minha conta",
    "preciso proteger minha conta",
    "preciso proteger minhas contas",
    "preciso proteger meus produtos bancarios",
    "bloquearam todos os meus produtos bancarios",
    "bloquearam minha conta e meus cartoes",
    "preciso bloquear o acesso aos meus produtos",
    "estou com uma emergencia",
    "estou com uma emergencia bancaria",
    "estou com uma emergencia na minha conta",
    "estou com uma emergencia com meus cartoes",
    "estou com uma emergencia nos meus produtos bancarios",
    "estou com um problema urgente de seguranca",
    "preciso de ajuda urgente",
    "urgente",
    "caí em um golpe",
    "me enganaram",
    "roubaram meu dinheiro",
    "estao se passando por mim",
    "roubaram minha identidade",
    "usaram meus dados para pedir um emprestimo",
    "fizeram um emprestimo no meu nome e nao fui eu",
    "tem um emprestimo no meu nome que nao solicitei",
    "apareceu um credito que nunca pedi",
    "alguem esta tentando fazer um emprestimo com meus dados",
    "preciso bloquear uma solicitacao de credito fraudulenta",
    "estao usando minha identidade para conseguir credito",
    "recebi um codigo de seguranca que nao solicitei",
    "recebi um alerta de acesso suspeito",
    "fui ameacado e preciso bloquear meus produtos",
    "nao consigo entrar na minha conta",
    "nao consigo acessar minha conta",
]


HUMAN_PHRASES = [
    # espanol
    "asesor",
    "asesora",
    "agente",
    "persona",
    "humano",
    "quiero hablar con alguien",
    "quiero hablar con una persona",
    "quiero hablar con un asesor",
    "quiero hablar con una asesora",
    "necesito un asesor",
    "necesito una persona",
    "comunicarme con un asesor",
    "pasame con un asesor",
    "pasame con una persona",
    "necesito hablar con alguien",
    "atencion al cliente",
    "atencion al usuario",
    "servicio al cliente",
    "representante del banco",
    "operador",
    "operadora",
    "hablar con un agente real",

    # portugues brasileiro
    "atendente",
    "atendente humano",
    "atendente humana",
    "quero falar com alguem",
    "quero falar com uma pessoa",
    "quero falar com um atendente",
    "quero falar com uma atendente",
    "preciso de um atendente",
    "preciso falar com alguem",
    "preciso falar com uma pessoa",
    "me transfira para um atendente",
    "me passa para um atendente",
    "quero falar com um humano",
    "atendimento ao cliente",
    "atendimento ao usuario",
    "servico de atendimento",
    "representante do banco",
    "operador",
    "operadora",
    "falar com uma pessoa de verdade",
]


NOT_ME_PHRASES = [
    # espanol
    "no reconozco",
    "pago no reconocido",
    "compra no reconocida",
    "movimiento no reconocido",
    "transaccion no reconocida",
    "no realice",
    "no hice",
    "yo no fui",
    "yo no hice esa compra",
    "esa compra no es mia",
    "no autorice esa compra",
    "no autorice ese pago",
    "no autorice esa transferencia",
    "no reconozco ese cobro",
    "no reconozco ese movimiento",
    "me hackearon",
    "me vaciaron la cuenta",
    "me sacaron plata",
    "me sacaron dinero sin permiso",
    "me hicieron una transferencia sin mi autorizacion",
    "hay compras que no son mias",
    "aparecio una compra que no hice",
    "me estan debitando sin autorizacion",
    "alguien uso mi tarjeta",
    "alguien entro a mi cuenta",
    "me hicieron fraude",
    "me robaron la plata",
    "me hicieron un retiro que no hice",

    # portugues brasileiro
    "nao reconheco",
    "pagamento nao reconhecido",
    "compra nao reconhecida",
    "movimentacao nao reconhecida",
    "transacao nao reconhecida",
    "nao fiz essa compra",
    "nao fui eu",
    "essa compra nao e minha",
    "nao autorizei essa compra",
    "nao autorizei esse pagamento",
    "nao autorizei essa transferencia",
    "nao reconheco essa cobranca",
    "nao reconheco essa movimentacao",
    "hackearam minha conta",
    "zeraram minha conta",
    "tiraram dinheiro da minha conta",
    "tiraram dinheiro sem minha autorizacao",
    "fizeram uma transferencia sem minha autorizacao",
    "tem compras que nao sao minhas",
    "apareceu uma compra que nao fiz",
    "estao debitando sem autorizacao",
    "alguem usou meu cartao",
    "alguem entrou na minha conta",
    "fizeram uma fraude",
    "roubaram meu dinheiro",
    "fizeram um saque que nao fiz",
]


CHARGE_ERROR_PHRASES = [
    # espanol
    "multiples veces",
    "varias veces",
    "dos veces",
    "tres veces",
    "cobro mal",
    "cobro incorrecto",
    "cobro erroneo",
    "cobro equivocado",
    "valor no coincide",
    "valor incorrecto",
    "valor equivocado",
    "me cobraron de mas",
    "me cobraron doble",
    "me cobraron dos veces",
    "me cobraron tres veces",
    "me cobraron varias veces",
    "me hicieron un doble cobro",
    "me aparece un cobro duplicado",
    "me cobraron algo diferente",
    "me cobraron mas de lo debido",
    "el valor cobrado esta mal",
    "el monto cobrado es incorrecto",
    "el cobro no corresponde",
    "me cobraron un valor diferente al acordado",
    "me descontaron dos veces",
    "pague una vez y me cobraron dos",
    "me cobraron una compra cancelada",
    "me cobraron una suscripcion cancelada",
    "me devolvieron menos dinero",
    "me cobraron una propina que no autorice",
    "el pago fue rechazado pero me descontaron",
    "me cobraron en dolares y pague en pesos",
    "la cuota llego mas cara",
    "el pago no se proceso pero me descontaron",
    "me cobraron un valor distinto al de la factura",
    "reembolso"

    # portugues brasileiro
    "varias vezes",
    "duas vezes",
    "tres vezes",
    "estorno",
    "cobranca errada",
    "cobranca incorreta",
    "cobranca indevida",
    "valor diferente",
    "valor incorreto",
    "valor errado",
    "me cobraram a mais",
    "me cobraram duas vezes",
    "me cobraram tres vezes",
    "me cobraram varias vezes",
    "fizeram uma cobranca duplicada",
    "apareceu uma cobranca duplicada",
    "me cobraram um valor diferente",
    "me cobraram mais do que deveriam",
    "o valor cobrado esta errado",
    "o valor cobrado esta incorreto",
    "a cobranca esta errada",
    "a cobranca nao corresponde",
    "me descontaram duas vezes",
    "paguei uma vez mas cobraram duas",
    "me cobraram por uma compra cancelada",
    "me cobraram por uma assinatura cancelada",
    "recebi menos dinheiro de volta",
    "cobraram uma gorjeta que nao autorizei",
    "o pagamento foi recusado mas descontaram o dinheiro",
    "me cobraram em dolares mas paguei em reais",
    "a parcela veio mais cara",
    "o pagamento nao foi processado mas descontaram",
    "me cobraram um valor diferente do da nota fiscal",
]


# ============================================================================
# Reglas de seguridad (ya están listas)
# ============================================================================

def is_emergency(text: str) -> bool:
    return contains_any(text, EMERGENCY_PHRASES)


def asks_for_human(text: str) -> bool:
    return contains_any(text, HUMAN_PHRASES)


# ============================================================================
# TU PARTE 2: el baseline
# ============================================================================

def baseline_understand(text: str) -> Understanding:
    """Clasifica solo con palabras clave. Devuelve el mismo formato que el LLM
    (Understanding), para poder evaluarlos de la misma forma.

    El orden importa: se queda con la PRIMERA regla que coincida, y las reglas
    van de más grave a menos grave para proteger primero el dinero del cliente.
    """
    if is_emergency(text):
        # 1. Tarjeta perdida/robada: alguien más puede estar usándola AHORA.
        intent = Intent.EMERGENCY
        confidence = 0.9
    elif contains_any(text, NOT_ME_PHRASES):
        # 2. Cargo que el cliente no hizo: posible fraude, hay que bloquear y disputar.
        intent = Intent.NOT_ME
        confidence = 0.9
    elif contains_any(text, CHARGE_ERROR_PHRASES):
        # 3. Cobro mal hecho de una compra propia: importante, pero no hay un ladrón.
        intent = Intent.CHARGE_ERROR
        confidence = 0.9
    else:
        # 4. No encontró ninguna palabra clave: no sabemos qué quiere.
        intent = Intent.OTHER
        confidence = 0.5   # baja a propósito: el router mostrará botones en vez de adivinar

    return Understanding(
        intent=intent,
        confidence=confidence,
        wants_human=asks_for_human(text),   # se revisa aparte: puede combinarse con cualquier intención
    )