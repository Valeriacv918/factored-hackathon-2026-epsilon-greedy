"""Supported curated customer locations -> IANA zones. Unknown locations fail closed."""
import unicodedata

def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD",value or "") if not unicodedata.combining(c)).strip().casefold()

ZONES = {
 ("colombia","antioquia","medellin"): "America/Bogota",
 ("colombia","atlantico","barranquilla"): "America/Bogota",
 ("colombia","bolivar","cartagena"): "America/Bogota",
 ("colombia","cundinamarca","bogota"): "America/Bogota",
 ("colombia","valle del cauca","cali"): "America/Bogota",
 ("argentina","buenos aires","la plata"): "America/Argentina/Buenos_Aires",
 ("argentina","ciudad autonoma de buenos aires","buenos aires"): "America/Argentina/Buenos_Aires",
 ("argentina","cordoba","cordoba"): "America/Argentina/Cordoba",
 ("argentina","mendoza","mendoza"): "America/Argentina/Mendoza",
 ("argentina","santa fe","rosario"): "America/Argentina/Cordoba",
 ("mexico","baja california","tijuana"): "America/Tijuana",
 ("mexico","ciudad de mexico","ciudad de mexico"): "America/Mexico_City",
 ("mexico","jalisco","guadalajara"): "America/Mexico_City",
 ("mexico","nuevo leon","monterrey"): "America/Monterrey",
 ("mexico","puebla","puebla"): "America/Mexico_City",
 ("mexico","queretaro","queretaro"): "America/Mexico_City",
}

def customer_timezone(location):
    key=tuple(normalized(location.get(k)) for k in ("country","state","city"))
    if key not in ZONES:
        raise ValueError("Customer location has no configured timezone.")
    return ZONES[key]
