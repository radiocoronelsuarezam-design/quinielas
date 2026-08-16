import os
import re
import sys
import time
import xml.dom.minidom
import requests
from google import genai
from google.genai import types, errors

# ==============================================================================
# CONFIGURACIÓN Y CREDENCIALES (Variables de Entorno en GitHub Actions)
# ==============================================================================
GEMINI_API_KEY = os.getenv("AI_KEY")
GITHUB_TOKEN = os.getenv("GIT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
NOMBRE_ARCHIVO_GIST = "quini_6_resultados.xml"

print(f"[DEBUG] AI_KEY presente: {bool(GEMINI_API_KEY)}")
print(f"[DEBUG] GITHUB_TOKEN presente: {bool(GITHUB_TOKEN)}")
print(f"[DEBUG] GIST_ID presente: {bool(GIST_ID)} (Valor recibido: '{GIST_ID}')")

if not GEMINI_API_KEY:
    print("[ERROR CRÍTICO] La variable AI_KEY no está configurada en los Secrets.", file=sys.stderr)
    sys.exit(1)

# Modelos a probar
MODELOS_GEMINI = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash"
]

try:
    print("[DEBUG] Inicializando cliente de Google GenAI...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("[DEBUG] Cliente inicializado correctamente.")
except Exception as e:
    print(f"[ERROR CRÍTICO] Error al inicializar el cliente de Gemini: {e}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)


def limpiar_id_gist(gist_input):
    if not gist_input:
        return ""
    if "/" in gist_input:
        return gist_input.rstrip("/").split("/")[-1].strip("[]()")
    return gist_input.strip("[]()")


def obtener_ultimo_sorteo():
    clean_gist_id = limpiar_id_gist(GIST_ID)
    print(f"[DEBUG] Gist ID limpio: '{clean_gist_id}'")
    
    if not clean_gist_id or not GITHUB_TOKEN:
        print("[DEBUG] GIST_ID o GITHUB_TOKEN faltantes. Se usará el sorteo base 3389.")
        return 3389

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        print(f"[DEBUG] Consultando API de GitHub Gist: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] HTTP Status Gist: {response.status_code}")
        
        if response.status_code == 200:
            files = response.json().get('files', {})
            if NOMBRE_ARCHIVO_GIST in files:
                content = files[NOMBRE_ARCHIVO_GIST]['content']
                match = re.search(r"<Sorteo>(\d+)</Sorteo>", content)
                if match:
                    sorteo_encontrado = int(match.group(1))
                    print(f"[DEBUG] Último sorteo hallado en Gist: {sorteo_encontrado}")
                    return sorteo_encontrado
            else:
                print(f"[DEBUG] El archivo '{NOMBRE_ARCHIVO_GIST}' no existe aún en el Gist.")
        else:
            print(f"[DEBUG] Error al leer Gist ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"[DEBUG] Excepción al consultar el Gist: {e}")
    
    return 3389


def procesar_pdf_con_gemini(pdf_bytes, num_sorteo):
    prompt_instrucciones = f"""
Eres un asistente experto en procesamiento visual de extractos oficiales de Lotería (Quini 6).
Analiza detenidamente la imagen/layout del PDF adjunto correspondiente al sorteo de Quini 6 y genera ÚNICAMENTE el código XML formateado de acuerdo con las siguientes reglas estrictas.

ESTRUCTURA XML REQUERIDA:
<DatosSorteo>
	<Version>1</Version>
	<Entidad>Lotería de Santa Fe</Entidad>
	<Juego>Quini 6</Juego>
	<Sorteo>{num_sorteo}</Sorteo>
	<FechaSorteo>[Fecha DD/MM/AAAA]</FechaSorteo>
	<PozoEstimado>[Monto numérico simple sin $ ni puntos]</PozoEstimado>
	<Extracto>
		<Modalidad>[Nombre de la modalidad]</Modalidad>
		<Moneda>[ARS o U$S]</Moneda>
		<Suerte>
			<N01>[2 dígitos]</N01>
		</Suerte>
		<Pozos>
			<Premio01>[Monto decimal]</Premio01>
		</Pozos>
		<Ganadores>
			<Ganadores01>[Ganadores 1° Premio]</Ganadores01>
		</Ganadores>
	</Extracto>
</DatosSorteo>

Retorna ÚNICAMENTE el código XML dentro de un bloque xml sin texto adicional.
"""

    for modelo in MODELOS_GEMINI:
        print(f"\n[DEBUG] Probando modelo: {modelo}...")
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
            print(f"[DEBUG] Respuesta recibida de {modelo} (primeros 100 caracteres): {repr(respuesta_texto[:100])}")
            
            match_xml = re.search(r"```xml\s*(.*?)\s*```", respuesta_texto, re.DOTALL)
            if match_xml:
                return match_xml.group(1).strip()
            
            if "<DatosSorteo>" in respuesta_texto:
                return respuesta_texto.strip()
            
            print(f"[DEBUG] Modelo {modelo} respondió pero sin etiquetas XML válidas.")
            
        except Exception as e:
            print(f"[DEBUG] Falló el modelo {modelo}. Error: {e}")
            
    raise RuntimeError("Ningún modelo de Gemini pudo procesar el PDF.")


def descargar_y_procesar(num_sorteo):
    url = f"https://loteriasantafe.gov.ar/uploads/extractosdigitales/Extracto_Sorteo_Q6_{num_sorteo}.pdf"
    print(f"[DEBUG] Descargando PDF desde: {url}")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers, timeout=15)
    print(f"[DEBUG] HTTP Status PDF: {response.status_code}")
    print(f"[DEBUG] Tamaño de respuesta: {len(response.content)} bytes")
    
    if response.status_code != 200:
        print(f"[DEBUG] El PDF del sorteo {num_sorteo} no existe o aún no fue publicado.")
        return None

    print(f"[DEBUG] PDF descargado con éxito. Enviando a Gemini...")
    xml_bruto = procesar_pdf_con_gemini(response.content, num_sorteo)
    return xml_bruto


if __name__ == "__main__":
    try:
        ultimo = obtener_ultimo_sorteo()
        nuevo = ultimo + 1
        print(f"[DEBUG] Objetivo actual -> Procesar Sorteo N° {nuevo}")
        
        xml_resultado = descargar_y_procesar(nuevo)
        
        if xml_resultado:
            print("[DEBUG] XML generado con éxito:")
            print(xml_resultado[:300] + "...\n(truncado)")
        else:
            print(f"[DEBUG] Finalizando: El sorteo {nuevo} no está listo para descargar.")
            
    except Exception as err:
        print(f"\n[ERROR CRÍTICO CAPTURADO DEPURACIÓN]: {err}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
