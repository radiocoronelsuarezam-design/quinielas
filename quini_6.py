import os
import re
import sys
import time
import requests
from google import genai

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
AI_KEY = os.environ.get("AI_KEY")
GITHUB_TOKEN = os.environ.get("GIT_TOKEN") or os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

NOMBRE_ARCHIVO_GIST = "quini_6_resultados.xml"
SORTEO_BASE_INICIAL = 3389

client = genai.Client(api_key=AI_KEY) if AI_KEY else None


def limpiar_id_gist(gist_id):
    if not gist_id:
        return ""
    gist_id = gist_id.strip()
    if "/" in gist_id:
        return gist_id.rstrip("/").split("/")[-1]
    return gist_id


# ==========================================
# GESTIÓN DE GITHUB GIST
# ==========================================
def obtener_ultimo_sorteo():
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not clean_gist_id or not GITHUB_TOKEN:
        print("[AVISO] GIST_ID o GIT_TOKEN no disponibles. Se asumirá el sorteo base inicial.")
        return SORTEO_BASE_INICIAL

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Python-Quini6-Script"
    }
    
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
            print(f"[DEBUG] El archivo '{NOMBRE_ARCHIVO_GIST}' aún no existe en el Gist.")
        else:
            print(f"[AVISO] No se pudo leer el Gist (HTTP {response.status_code})")
    except Exception as e:
        print(f"[AVISO] Excepción al consultar el Gist: {e}")
        
    return SORTEO_BASE_INICIAL


def actualizar_github_gist(contenido_xml):
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not GITHUB_TOKEN or not clean_gist_id:
        print("[AVISO] Token o Gist ID no configurado. Se omite la actualización del Gist.")
        return False

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Python-Quini6-Script"
    }
    payload = {
        "files": {
            NOMBRE_ARCHIVO_GIST: {
                "content": contenido_xml
            }
        }
    }
    
    try:
        response = requests.patch(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            print("[ÉXITO] Gist actualizado correctamente en GitHub.")
            return True
        else:
            print(f"[ERROR] Falló la actualización del Gist: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Excepción al actualizar el Gist: {e}")
        return False


# ==========================================
# PROCESAMIENTO CON GEMINI
# ==========================================
def procesar_pdf_con_gemini(pdf_bytes, num_sorteo):
    print(f"[DEBUG] Procesando PDF con Gemini para sorteo {num_sorteo}...")
    prompt = f"""
    Analiza detalladamente este extracto oficial de Quini 6 (Sorteo N° {num_sorteo}).
    Extrae todos los resultados y genera un documento XML estricto con la siguiente estructura:
    
    <Quini6>
      <Sorteo>{num_sorteo}</Sorteo>
      <Fecha>DD/MM/AAAA</Fecha>
      <Modalidades>
        <Tradicional>
          <Numeros>00,00,00,00,00,00</Numeros>
          <Ganadores6Aciertos>0</Ganadores6Aciertos>
          <Premio6Aciertos>0.00</Premio6Aciertos>
        </Tradicional>
        <LaSegunda>
          <Numeros>00,00,00,00,00,00</Numeros>
          <Ganadores6Aciertos>0</Ganadores6Aciertos>
          <Premio6Aciertos>0.00</Premio6Aciertos>
        </LaSegunda>
        <Revancha>
          <Numeros>00,00,00,00,00,00</Numeros>
          <Ganadores6Aciertos>0</Ganadores6Aciertos>
          <Premio6Aciertos>0.00</Premio6Aciertos>
        </Revancha>
        <SiempreSale>
          <Numeros>00,00,00,00,00,00</Numeros>
          <Ganadores>0</Ganadores>
          <Premio>0.00</Premio>
        </SiempreSale>
        <PozoExtra>
          <Ganadores>0</Ganadores>
          <Premio>0.00</Premio>
        </PozoExtra>
      </Modalidades>
    </Quini6>

    Responde ÚNICAMENTE con el código XML sin bloques de markdown.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            genai.types.Part.from_bytes(
                data=pdf_bytes,
                mime_type='application/pdf'
            ),
            prompt
        ]
    )
    return response.text.strip()


def formatear_xml(xml_texto):
    xml_limpio = re.sub(r"^```xml\s*", "", xml_texto, flags=re.MULTILINE)
    xml_limpio = re.sub(r"^```\s*", "", xml_limpio, flags=re.MULTILINE)
    return xml_limpio.strip()


def obtener_numero_sorteo_del_xml(xml_texto):
    match = re.search(r"<Sorteo>(\d+)</Sorteo>", xml_texto)
    return int(match.group(1)) if match else None


# ==========================================
# DESCARGA DIRECTA (SESIÓN NAVEGADOR)
# ==========================================
def descargar_pdf_directo(num_sorteo):
    """Realiza la descarga directa del PDF con una sesión de solicitudes simulando navegador."""
    url = f"https://loteriasantafe.gov.ar/uploads/extractosdigitales/Extracto_Sorteo_Q6_{num_sorteo}.pdf"
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://loteriasantafe.gov.ar/'
    }
    
    print(f"[DEBUG] Solicitando PDF directo para sorteo N° {num_sorteo}...")
    try:
        # Petición previa para establecer cookies del servidor si las requiere
        session.get("https://loteriasantafe.gov.ar/", headers=headers, timeout=10)
        response = session.get(url, headers=headers, timeout=20)
        
        print(f"[DEBUG] HTTP Status Conexión Directa: {response.status_code}")
        if response.status_code == 200 and response.content.startswith(b'%PDF'):
            return response.content
        elif response.status_code == 404:
            print(f"[DEBUG] El PDF del sorteo {num_sorteo} no existe aún en el servidor.")
    except Exception as e:
        print(f"[ERROR] Error al realizar conexión directa: {e}")
        
    return None


def descargar_y_procesar(num_sorteo):
    pdf_bytes = descargar_pdf_directo(num_sorteo)
    
    if pdf_bytes:
        xml_bruto = procesar_pdf_con_gemini(pdf_bytes, num_sorteo)
        xml_formateado = formatear_xml(xml_bruto)
        sorteo_real = obtener_numero_sorteo_del_xml(xml_formateado) or num_sorteo
        return sorteo_real, xml_formateado
        
    return None, None


# ==========================================
# FLUJO PRINCIPAL DE EJECUCIÓN
# ==========================================
def main():
    print("=== INICIANDO PROCESAMIENTO DE QUINI 6 ===")
    if not AI_KEY:
        print("[ERROR CRÍTICO] La variable AI_KEY no está configurada. Abortando.")
        sys.exit(1)
        
    ultimo_sorteo_registrado = obtener_ultimo_sorteo()
    sorteo_a_buscar = ultimo_sorteo_registrado + 1
    
    print(f"[DEBUG] Sorteo a procesar: N° {sorteo_a_buscar}")
    
    sorteo_procesado, xml_resultado = descargar_y_procesar(sorteo_a_buscar)
    
    if xml_resultado:
        print(f"[ÉXITO] Sorteo {sorteo_procesado} procesado exitosamente por la AI.")
        actualizar_github_gist(xml_resultado)
    else:
        print(f"[INFO] El PDF del sorteo {sorteo_a_buscar} no se pudo obtener directamente.")
        
    print("=== FINALIZADO ===")


if __name__ == "__main__":
    main()
