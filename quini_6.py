import os
import re
import sys
import time
import urllib.parse
import requests
import google.generativeai as genai

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
AI_KEY = os.environ.get("AI_KEY")
GITHUB_TOKEN = os.environ.get("GIT_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

NOMBRE_ARCHIVO_GIST = "quini_6_resultados.xml"
SORTEO_BASE_INICIAL = 3389

# Configurar SDK de Gemini si el API Key está presente
if AI_KEY:
    genai.configure(api_key=AI_KEY)


def limpiar_id_gist(gist_id):
    """Extrae únicamente el hash del Gist si se pasó una URL completa."""
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
    """Consulta el archivo XML almacenado en el Gist para obtener el último número de sorteo procesado."""
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
            print(f"[DEBUG] El archivo '{NOMBRE_ARCHIVO_GIST}' aún no existe en el Gist. Se iniciará desde el base.")
        elif response.status_code == 404:
            print("[DEBUG] El Gist especificado no fue encontrado o está vacío. Se asumirá el sorteo base.")
        else:
            print(f"[AVISO] No se pudo leer el Gist (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        print(f"[AVISO] Excepción al consultar el Gist: {e}")
        
    return SORTEO_BASE_INICIAL


def actualizar_github_gist(contenido_xml):
    """Actualiza el archivo en GitHub Gist con el contenido XML procesado."""
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
    
    print(f"[DEBUG] Enviando PATCH a API de GitHub Gist: {url}")
    try:
        response = requests.patch(url, json=payload, headers=headers, timeout=15)
        print(f"[DEBUG] Status Code Respuesta Gist: {response.status_code}")
        
        if response.status_code == 200:
            print("[ÉXITO] Gist actualizado correctamente en GitHub.")
            return True
        else:
            print(f"[ERROR] Falló la actualización del Gist: HTTP {response.status_code}")
            print(f"[ERROR Detalle]: {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Excepción al actualizar el Gist: {e}")
        return False


# ==========================================
# PROCESAMIENTO DE CONTEXTO Y GEMINI
# ==========================================
def procesar_pdf_con_gemini(pdf_bytes, num_sorteo):
    """Envia el PDF a Gemini 1.5 Pro/Flash para extraer los resultados en XML."""
    print(f"[DEBUG] Procesando el PDF del sorteo N° {num_sorteo} con Gemini...")
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
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

    Responde ÚNICAMENTE con el código XML. No agregues bloques de markdown como ```xml ... ``` ni comentarios adicionales.
    """
    
    pdf_part = {
        "mime_type": "application/pdf",
        "data": pdf_bytes
    }
    
    response = model.generate_content([prompt, pdf_part])
    return response.text.strip()


def formatear_xml(xml_texto):
    """Limpia etiquetas de markdown sobrantes que Gemini pueda incluir."""
    xml_limpio = re.sub(r"^```xml\s*", "", xml_texto, flags=re.MULTILINE)
    xml_limpio = re.sub(r"^```\s*", "", xml_limpio, flags=re.MULTILINE)
    return xml_limpio.strip()


def obtener_numero_sorteo_del_xml(xml_texto):
    """Extrae el número de sorteo presente dentro del XML procesado."""
    match = re.search(r"<Sorteo>(\d+)</Sorteo>", xml_texto)
    if match:
        return int(match.group(1))
    return None


# ==========================================
# DESCARGA DEL PDF VÍA CORSPROXY
# ==========================================
def descargar_y_procesar(num_sorteo):
    """Descarga el PDF del servidor de la lotería utilizando únicamente CorsProxy para evadir bloqueos de IP."""
    url_directa = f"https://loteriasantafe.gov.ar/uploads/extractosdigitales/Extracto_Sorteo_Q6_{num_sorteo}.pdf"
    
    # Construcción de la URL pasando únicamente por CorsProxy
    url_encoded = urllib.parse.quote(url_directa, safe='')
    url_proxy = f"https://corsproxy.io/?{url_encoded}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8'
    }
    
    print(f"[DEBUG] Solicitando PDF a través de CorsProxy para el sorteo N° {num_sorteo}...")
    
    try:
        response = requests.get(url_proxy, headers=headers, timeout=20, allow_redirects=True)
        print(f"[DEBUG] HTTP Status CorsProxy: {response.status_code}")
        
        # Validar si el contenido devuelto es realmente un PDF válido
        if response.status_code == 200 and (response.content.startswith(b'%PDF') or len(response.content) > 5000):
            print(f"[ÉXITO] PDF descargado correctamente ({len(response.content)} bytes). Enviando a Gemini...")
            xml_bruto = procesar_pdf_con_gemini(response.content, num_sorteo)
            xml_formateado = formatear_xml(xml_bruto)
            sorteo_real = obtener_numero_sorteo_del_xml(xml_formateado) or num_sorteo
            return sorteo_real, xml_formateado
        elif response.status_code == 404:
            print(f"[DEBUG] El PDF del sorteo {num_sorteo} aún no ha sido publicado en el servidor de la lotería.")
            return None, None
        else:
            print(f"[AVISO] Respuesta o contenido no válido del proxy (HTTP {response.status_code}).")
            
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Falló la conexión con CorsProxy: {e}")
        
    return None, None


# ==========================================
# FLUJO PRINCIPAL DE EJECUCIÓN
# ==========================================
def main():
    print("=== INICIANDO PROCESAMIENTO DE QUINI 6 ===")
    print(f"[DEBUG] AI_KEY configurada: {bool(AI_KEY)}")
    print(f"[DEBUG] GIT_TOKEN configurado: {bool(GITHUB_TOKEN)}")
    print(f"[DEBUG] GIST_ID configurado: {bool(GIST_ID)}")
    
    if not AI_KEY:
        print("[ERROR CRÍTICO] La variable AI_KEY no está configurada. Abortando.")
        sys.exit(1)
        
    # 1. Obtener el último sorteo que tenemos procesado en el Gist
    ultimo_sorteo_registrado = obtener_ultimo_sorteo()
    sorteo_a_buscar = ultimo_sorteo_registrado + 1
    
    print(f"[DEBUG] Sorteo a procesar: N° {sorteo_a_buscar}")
    
    # 2. Descargar y procesar el nuevo extracto PDF
    sorteo_procesado, xml_resultado = descargar_y_procesar(sorteo_a_buscar)
    
    if xml_resultado:
        print(f"[ÉXITO] Sorteo {sorteo_procesado} procesado exitosamente por la AI.")
        # 3. Actualizar el contenido en GitHub Gist
        actualizar_github_gist(xml_resultado)
    else:
        print(f"[INFO] El sorteo {sorteo_a_buscar} no está disponible todavía en el servidor de la lotería.")
        
    print("=== FINALIZADO SIN ERRORES ===")

if __name__ == "__main__":
    main()
