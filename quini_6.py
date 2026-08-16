import os
import re
import sys
import time
import traceback
import xml.dom.minidom
import requests
from google import genai
from google.genai import types, errors

# ==============================================================================
# CONFIGURACIÓN Y CREDENCIALES (Variables de Entorno)
# ==============================================================================
GEMINI_API_KEY = os.getenv("AI_KEY")
GITHUB_TOKEN = os.getenv("GIT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
NOMBRE_ARCHIVO_GIST = "quini_6_resultados.xml"

print("=== INICIANDO PROCESAMIENTO DE QUINI 6 ===")
print(f"[DEBUG] AI_KEY configurada: {bool(GEMINI_API_KEY)}")
print(f"[DEBUG] GIT_TOKEN configurado: {bool(GITHUB_TOKEN)}")
print(f"[DEBUG] GIST_ID configurado: {bool(GIST_ID)}")

if not GEMINI_API_KEY:
    print("[ERROR CRÍTICO] La variable AI_KEY no está presente.", file=sys.stderr)
    sys.exit(1)

# LISTA DE MODELOS VIGENTES EN ORDEN DE RESPALDO (Fallback)
MODELOS_GEMINI = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash"
]

client = genai.Client(api_key=GEMINI_API_KEY)


def limpiar_id_gist(gist_input):
    """Extrae el hash alfanumérico si se proporcionó una URL completa."""
    if not gist_input:
        return ""
    if "/" in gist_input:
        return gist_input.rstrip("/").split("/")[-1].strip("[]()")
    return gist_input.strip("[]()")


def obtener_ultimo_sorteo():
    """Consulta el archivo XML almacenado en el Gist para obtener el último número procesado."""
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not clean_gist_id or not GITHUB_TOKEN:
        print("[AVISO] GIST_ID o GIT_TOKEN no disponibles. Se utilizará sorteo base 3389.")
        return 3389

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        print(f"[DEBUG] Consultando Gist: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            files = response.json().get('files', {})
            if NOMBRE_ARCHIVO_GIST in files:
                content = files[NOMBRE_ARCHIVO_GIST]['content']
                match = re.search(r"<Sorteo>(\d+)</Sorteo>", content)
                if match:
                    sorteo = int(match.group(1))
                    print(f"[DEBUG] Último sorteo registrado en Gist: {sorteo}")
                    return sorteo
        else:
            print(f"[AVISO] No se pudo leer el Gist (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"[AVISO] Excepción al consultar el Gist: {e}")
    return 3389


def procesar_pdf_con_gemini(pdf_bytes, num_sorteo):
    """Envia el PDF del extracto a Gemini para estructurar el resultado en XML."""
    prompt_instrucciones = f"""
Eres un asistente experto en procesamiento visual de extractos oficiales de Lotería (Quini 6).
Analiza detenidamente la imagen/layout del PDF adjunto correspondiente al sorteo de Quini 6 y genera ÚNICAMENTE el código XML formateado de acuerdo con las siguientes reglas estrictas.

REGLAS DE LECTURA VISUAL Y ESTRUCTURA (MUY IMPORTANTE):
1. **MODALIDADES PRINCIPALES (Tradicional Primer Sorteo, Tradicional La Segunda, Revancha)**:
   Presentan la misma estructura de datos:
   - 1° Premio (6 aciertos): Pozo y cantidad de apuestas ganadoras.
   - 2° Premio (5 aciertos): Pozo y cantidad de apuestas ganadoras.
   - 3° Premio (4 aciertos): Pozo y cantidad de apuestas ganadoras.
   - Estímulo: Premio y ganadores del estímulo.

2. **SIEMPRE SALE**:
   - Muestra obligatoriamente la cantidad de aciertos máximos conseguidos (etiqueta <Aciertos>), el pozo y la cantidad de apuestas ganadoras de esa modalidad, junto con su respectivo estímulo.

3. **PREMIO EXTRA**:
   - Incluye los 18 números ganadores que componen el Premio Extra (los 6 de Primer Sorteo + los 6 de La Segunda + los 6 de Revancha), INCLUYENDO los números repetidos/tachados (N01 hasta N18).

ESTRUCTURA XML REQUERIDA:
<DatosSorteo>
	<Version>1</Version>
	<Entidad>Lotería de Santa Fe</Entidad>
	<Juego>Quini 6</Juego>
	<Sorteo>{num_sorteo}</Sorteo>
	<FechaSorteo>[Fecha DD/MM/AAAA]</FechaSorteo>
	<PozoEstimado>[Monto numérico simple sin $ ni puntos, ej: 12500000000.00]</PozoEstimado>
	<Extracto>
		<Modalidad>[Nombre de la modalidad]</Modalidad>
		<Moneda>[ARS o U$S]</Moneda>
		<!-- Si es Siempre Sale agregar: <Aciertos>[número de aciertos]</Aciertos> -->
		<Suerte>
			<N01>[2 dígitos]</N01>
			...
		</Suerte>
		<Pozos>
			<Premio01>[Monto decimal, ej: 7064308818.00]</Premio01>
			<Premio02>[Monto decimal]</Premio02>
			<Premio03>[Monto decimal]</Premio03>
			<Estimulo>[Monto decimal]</Estimulo>
		</Pozos>
		<Ganadores>
			<Ganadores01>[Ganadores 1° Premio]</Ganadores01>
			<Ganadores02>[Ganadores 2° Premio]</Ganadores02>
			<Ganadores03>[Ganadores 3° Premio]</Ganadores03>
			<GanadoresEstimulo>[Ganadores Estímulo]</GanadoresEstimulo>
		</Ganadores>
	</Extracto>
</DatosSorteo>

REGLAS DE FORMATO NUMÉRICO:
- Sin símbolos de moneda ('$'), sin puntos separadores de miles y con punto decimal para centavos (ej: 7064308818.00).
- Si una categoría es "VACANTE", poner 0 en la cantidad de ganadores.
- Retorna ÚNICAMENTE el código XML dentro de un bloque xml sin texto adicional.
"""

    for modelo in MODELOS_GEMINI:
        print(f"\n[DEBUG] Probando modelo Gemini: {modelo}...")
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=[
                    types.Part.from_bytes(
                        data=pdf_bytes,
                        mime_type='application/pdf',
                    ),
                    prompt_instrucciones
                ],
                config=types.GenerateContentConfig(temperature=0.0)
            )
            
            respuesta_texto = response.text
            
            match_xml = re.search(r"```xml\s*(.*?)\s*```", respuesta_texto, re.DOTALL)
            if match_xml:
                print(f"[ÉXITO] Respuesta generada con {modelo}")
                return match_xml.group(1).strip()
            
            if "<DatosSorteo>" in respuesta_texto:
                print(f"[ÉXITO] Respuesta generada con {modelo}")
                return respuesta_texto.strip()
            
            print(f"[AVISO] El modelo {modelo} respondió pero sin el formato XML esperado.")
            
        except Exception as e:
            print(f"[AVISO] Error con el modelo {modelo}: {e}")
            
    raise RuntimeError("Ningún modelo de Gemini pudo procesar el documento PDF.")


def formatear_xml(xml_string):
    """Normaliza nombres de modalidades y aplica formato limpio con sangría."""
    def reemplazar_modalidad(match):
        texto = match.group(1).upper().strip()
        if "PRIMER" in texto or ("TRADICIONAL" in texto and "SEGUNDA" not in texto):
            return "<Modalidad>Tradicional Primer Sorteo</Modalidad>"
        elif "SEGUNDA" in texto:
            return "<Modalidad>Tradicional La Segunda</Modalidad>"
        elif "REVANCHA" in texto:
            return "<Modalidad>Revancha</Modalidad>"
        elif "SIEMPRE" in texto or "SALE" in texto:
            return "<Modalidad>Siempre Sale</Modalidad>"
        elif "EXTRA" in texto:
            return "<Modalidad>Premio Extra</Modalidad>"
        return match.group(0)

    xml_normalizado = re.sub(r"<Modalidad>(.*?)</Modalidad>", reemplazar_modalidad, xml_string, flags=re.IGNORECASE)

    lineas_limpias = [line.strip() for line in xml_normalizado.splitlines() if line.strip()]
    xml_reunido = "".join(lineas_limpias)
    
    dom = xml.dom.minidom.parseString(xml_reunido)
    pretty_xml = dom.toprettyxml(indent="\t")
    
    lineas_filtradas = [line for line in pretty_xml.splitlines() if line.strip()]
    return "\n".join(lineas_filtradas)


def obtener_numero_sorteo_del_xml(xml_string):
    if not xml_string:
        return None
    match = re.search(r"<Sorteo>(\d+)</Sorteo>", xml_string)
    if match:
        return int(match.group(1))
    return None


def descargar_y_procesar(num_sorteo):
    """Descarga el PDF del servidor oficial reintentando en caso de timeout."""
    url = f"https://loteriasantafe.gov.ar/uploads/extractosdigitales/Extracto_Sorteo_Q6_{num_sorteo}.pdf"
    print(f"[DEBUG] Descargando PDF desde: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8'
    }
    
    for intento in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=20)
            print(f"[DEBUG] HTTP Status PDF (Intento {intento + 1}): {response.status_code}")
            
            if response.status_code == 200:
                print(f"[DEBUG] PDF descargado correctamente ({len(response.content)} bytes). Enviando a Gemini...")
                xml_bruto = procesar_pdf_con_gemini(response.content, num_sorteo)
                xml_formateado = formatear_xml(xml_bruto)
                sorteo_real = obtener_numero_sorteo_del_xml(xml_formateado) or num_sorteo
                return sorteo_real, xml_formateado
            elif response.status_code == 404:
                print(f"[DEBUG] El PDF del sorteo {num_sorteo} aún no ha sido publicado.")
                return None, None
            else:
                print(f"[AVISO] Respuesta del servidor: HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"[AVISO] Timeout en intento {intento + 1}. Reintentando en 5 segundos...")
            time.sleep(5)
        except Exception as e:
            print(f"[AVISO] Error al conectar con la Lotería (Intento {intento + 1}): {e}")
            time.sleep(5)
            
    return None, None


def actualizar_github_gist(contenido_xml):
    """Actualiza el archivo en GitHub Gist con el contenido XML procesado."""
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not GITHUB_TOKEN or not clean_gist_id:
        print("[AVISO] Token o Gist ID no configurado. Se omite la actualización del Gist.")
        return

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "files": {
            NOMBRE_ARCHIVO_GIST: {
                "content": contenido_xml
            }
        }
    }
    
    print("[DEBUG] Actualizando archivo en GitHub Gist...")
    response = requests.patch(url, json=payload, headers=headers, timeout=10)
    
    if response.status_code == 200:
        print("[ÉXITO] Gist actualizado correctamente.")
    else:
        print(f"[ERROR] Error al actualizar el Gist ({response.status_code}): {response.text}")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
            nuevo = int(sys.argv[1])
        else:
            ultimo = obtener_ultimo_sorteo()
            nuevo = ultimo + 1
        
        print(f"[DEBUG] Sorteo a procesar: N° {nuevo}")
        sorteo_final, xml_resultado = descargar_y_procesar(nuevo)
        
        if xml_resultado:
            archivo_salida = f"Q6_{sorteo_final}.xml"
            with open(archivo_salida, "w", encoding="utf-8") as f:
                f.write(xml_resultado)
                
            print(f"[ÉXITO] XML guardado localmente: {archivo_salida}")
            actualizar_github_gist(xml_resultado)
        else:
            print(f"[INFO] El sorteo {nuevo} no está disponible todavía en el servidor de la lotería.")
            # Finalización sin error para indicar una espera normal
            sys.exit(0)

    except Exception as err:
        print(f"\n[ERROR CRÍTICO CAPTURADO]: {err}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
