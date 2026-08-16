import io
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import xml.dom.minidom
import requests
from google import genai
from google.genai import types, errors

# ==============================================================================
# CONFIGURACIÓN Y CREDENCIALES (Obtenidas desde GitHub Secrets)
# ==============================================================================
GEMINI_API_KEY = os.getenv("AI_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIST_ID = os.getenv("GIST_ID")
NOMBRE_ARCHIVO_GIST = "quini_6_resultados.xml"

# Validar que las variables críticas estén presentes
if not GEMINI_API_KEY:
    raise ValueError("Error: La variable de entorno AI_KEY no está configurada.")

# LISTA DE MODELOS VIGENTES EN ORDEN DE RESPALDO (Fallback)
MODELOS_GEMINI = [
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest"
]

# INICIALIZACIÓN DEL CLIENTE DE GEMINI
client = genai.Client(api_key=GEMINI_API_KEY)


def limpiar_id_gist(gist_input):
    """Extrae el hash alfanumérico si se pegó una URL completa."""
    if not gist_input:
        return ""
    if "/" in gist_input:
        return gist_input.rstrip("/").split("/")[-1].strip("[]()")
    return gist_input.strip("[]()")


def obtener_ultimo_sorteo():
    """
    Consulta el archivo XML almacenado en el Gist de GitHub
    para obtener el último número de sorteo procesado.
    """
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not clean_gist_id or not GITHUB_TOKEN:
        print("Aviso: GIST_ID o GITHUB_TOKEN no configurados. Se tomará valor base.")
        return 3389

    url = f"https://api.github.com/gists/{clean_gist_id}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            content = response.json()['files'][NOMBRE_ARCHIVO_GIST]['content']
            match = re.search(r"<Sorteo>(\d+)</Sorteo>", content)
            if match:
                return int(match.group(1))
    except Exception as e:
        print(f"No se pudo consultar el Gist para el último sorteo: {e}")
    return 3389


def procesar_pdf_con_gemini(pdf_bytes, num_sorteo):
    """
    Envía el PDF en binario a Google Gemini recorriendo la lista de modelos.
    """
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
   (Nota: No incluyas los valores de "Premio por Apuesta" en el XML, ya que se calculan externamente).

2. **SIEMPRE SALE**:
   - Muestra obligatoriamente la cantidad de aciertos máximos conseguidos (etiqueta <Aciertos>), el pozo y la cantidad de apuestas ganadoras de esa modalidad, junto con su respectivo estímulo.

3. **PREMIO EXTRA**:
   - En la sección "Premio Extra", NO omitas NINGÚN número. Incluye los 18 números ganadores que componen el Premio Extra (los 6 de Primer Sorteo + los 6 de La Segunda + los 6 de Revancha), INCLUYENDO los números repetidos/tachados (N01 hasta N18).

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

    max_intentos_por_modelo = 2

    for modelo in MODELOS_GEMINI:
        print(f"\nProcesando PDF con modelo: {modelo}...")
        for intento in range(max_intentos_por_modelo):
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
                    config=types.GenerateContentConfig(
                        temperature=0.0
                    )
                )
                
                respuesta_texto = response.text
                
                match_xml = re.search(r"```xml\s*(.*?)\s*```", respuesta_texto, re.DOTALL)
                if match_xml:
                    print(f"¡Éxito obtenido con {modelo}!")
                    return match_xml.group(1).strip()
                
                match_gen = re.search(r"```\s*(.*?)\s*```", respuesta_texto, re.DOTALL)
                if match_gen and "<DatosSorteo>" in match_gen.group(1):
                    print(f"¡Éxito obtenido con {modelo}!")
                    return match_gen.group(1).strip()

                match_tag = re.search(r"(<DatosSorteo>.*?</DatosSorteo>)", respuesta_texto, re.DOTALL)
                if match_tag:
                    print(f"¡Éxito obtenido con {modelo}!")
                    return match_tag.group(1).strip()
                
                if "<DatosSorteo>" in respuesta_texto:
                    print(f"¡Éxito obtenido con {modelo}!")
                    return respuesta_texto.strip()
                
                print(f"El modelo {modelo} respondió pero sin el formato XML válido.")
                
            except (errors.ServerError, errors.ClientError) as e:
                print(f"Aviso con modelo {modelo}: {e}")
                if ("503" in str(e) or "429" in str(e)) and intento < max_intentos_por_modelo - 1:
                    print("Esperando 5 segundos para reintentar el mismo modelo...")
                    time.sleep(5)
                else:
                    print("Pasando al siguiente modelo de respaldo...")
                    break
                    
            except Exception as e:
                print(f"Error inesperado con {modelo}: {e}")
                break

    raise RuntimeError("Todos los modelos de Gemini fallaron o no están disponibles.")


def formatear_xml(xml_string):
    """Normaliza modalidades y embellece el XML."""
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
    """Extrae el número de sorteo real desde el XML generado."""
    match = re.search(r"<Sorteo>(\d+)</Sorteo>", match_text if (match_text := xml_string) else "")
    if match:
        return int(match.group(1))
    return None


def descargar_y_procesar_con_gemini(num_sorteo):
    """Descarga el PDF desde la Lotería de Santa Fe y solicita la extracción a Gemini."""
    url = f"https://loteriasantafe.gov.ar/uploads/extractosdigitales/Extracto_Sorteo_Q6_{num_sorteo}.pdf"
    print(f"Intentando descargar: {url}")
    response = requests.get(url, timeout=15)
    
    if response.status_code != 200:
        print("Sorteo no disponible aún.")
        return None, None

    xml_bruto = procesar_pdf_con_gemini(response.content, num_sorteo)
    xml_formateado = formatear_xml(xml_bruto)
    sorteo_real = obtener_numero_sorteo_del_xml(xml_formateado) or num_sorteo
    
    return sorteo_real, xml_formateado


def actualizar_github_gist(contenido_xml):
    """Actualiza el archivo en GitHub Gist vía API REST."""
    clean_gist_id = limpiar_id_gist(GIST_ID)
    if not GITHUB_TOKEN or not clean_gist_id:
        print("Aviso: Token o Gist ID no configurado. XML generado únicamente a nivel local.")
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
    
    print("Actualizando archivo en GitHub Gist...")
    response = requests.patch(url, json=payload, headers=headers, timeout=10)
    
    if response.status_code == 200:
        print("¡Gist actualizado exitosamente!")
    else:
        print(f"Error al actualizar el Gist. Código HTTP: {response.status_code}")
        print(f"Respuesta: {response.text}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        nuevo = int(sys.argv[1])
    else:
        ultimo = obtener_ultimo_sorteo()
        nuevo = ultimo + 1
    
    print(f"Buscando y procesando Sorteo {nuevo} con Gemini...")
    sorteo_final, xml_resultado = descargar_y_procesar_con_gemini(nuevo)
    
    if xml_resultado:
        archivo_salida = f"Q6_{sorteo_final}.xml"
        with open(archivo_salida, "w", encoding="utf-8") as f:
            f.write(xml_resultado)
            
        print(f"XML guardado localmente: {archivo_salida}")
        actualizar_github_gist(xml_resultado)
    else:
        print("El sorteo no está disponible todavía en el servidor de la lotería.")