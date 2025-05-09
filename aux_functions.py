import time
import re # regular expressions
import pandas as pd
import requests
import xml.etree.ElementTree as ET

API_URL = "https://www.biodiversitylibrary.org/api3"
"""
Funciones utilizadas para extracción y manipulación de datos
Métodos de la Api utilizados:
- GetNameMetadata (Para buscar todas las páginas donde exista información de una especie, la respuesta de la API se guarda en una lista)
- GetPageMetadata(Para buscar información y texto de una página en específico)
- GetItemMetadata(Para conseguir los metadatos de un item, en este caso una página)
"""

failed_pages = []
def get_page_metadata(page_id, api_key):
    params = {
        "op": "GetPageMetadata",
        "pageid": page_id,
        "ocr": "t",
        "names": "t",
        "format": "xml",
        "apikey": api_key
    }
    try:
        response = requests.get(API_URL, params=params, timeout=25)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error obteniendo página {page_id}: {str(e)}")
        failed_pages.append(page_id)
        return None

def get_name_metadata(name, api_key):
    params = {
        "op": "GetNameMetadata",
        "name": name,
        "format": "xml",
        "apikey": api_key
    }
    try:
        response = requests.get(API_URL, params=params, timeout=25)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error obteniendo metadatos para {name}: {str(e)}")
        return None


failed_items = []
def get_item_metadata(item_ID, api_key):
    """Obtiene metadatos para un ítem (publicación, página, lo que tenga ID en general)."""
    if(item_ID in failed_items): return None
    params = {
        "op": "GetItemMetadata",
        "id": item_ID,
        "idtype": "bhl",
        "pages": "f",  #Data already retrieved, doesn´t need to ask it again
        "ocr": "f",
        "parts": "f",
        "format": "xml",
        "apikey": api_key
    }
    try:
        response = requests.get(API_URL, params=params, timeout=25)
        response.raise_for_status()
        return response.text
    except Exception as e:
        failed_items.append(item_ID)
        print(f"Error obteniendo metadatos para {item_ID}: {str(e)}")
        return None

"""
Funciones de extracción de datos en un xml
- Todas las funciones necesarias para poder procesar y guardar los datos de los xml obtenidos usando las funciones anteriores.
"""

def conseguirListaPaginas(xml_data):
    """Parsea XML y extrae información relevante."""
    if not xml_data:
        return []
    try:
        root = ET.fromstring(xml_data)
        return [page_id.text for page_id in root.findall('.//PageID')]
    except Exception as e:
        print(f"Error parseando XML: {str(e)}")
        return []

def extract_idItem_metadata(xml_data):
    """Extrae metadatos importantes de la respuessta de getItemIDMetadata"""
    if not xml_data:
        return {}
    try:
        root = ET.fromstring(xml_data)
        return {
            'Fuente': root.find('.//Source').text if root.find('.//Source') is not None else None,
            'IdFuente': root.find('.//SourceIdentifier').text if root.find('.//SourceIdentifier') is not None else None,
            'Institución': root.find('.//HoldingInstitution').text if root.find('.//HoldingInstitution') is not None else None,
            'Idioma': root.find('.//Language').text if root.find('.//Language') is not None else None,
            'Derechos': root.find('.//Rights').text if root.find('.//Rights') is not None else None,
            'Copyright': root.find('.//CopyrightStatus').text if root.find('.//CopyrightStatus') is not None else None,
        }
    except Exception as e:
        print(f"Error extrayendo metadatos: {str(e)}")
        return {}


def extract_page_metadata(xml_data):
    """Extrae metadatos importantes de la página."""
    if not xml_data:
        return {}
    try:
        root = ET.fromstring(xml_data)
        return {
            'Volumen': root.find('.//Volume').text if root.find('.//Volume') is not None else None,
            'Año': root.find('.//Year').text if root.find('.//Year') is not None else None,
        }
    except Exception as e:
        print(f"Error extrayendo metadatos: {str(e)}")
        return {}

"""
Función de limpieza de texto
    Se busca dejar los párrafos lo más limpio posible para un uso adecuado, no solo se eliminan caracteres o palabras residuales de XML, sino que se trata de
    eliminar lenguaje de máquina no procesado y reemplazar caracteres extravagantes por caracteres de uso común.
"""

def clean_paragraph(text):
    if not text:
        return ""

    patterns = [
        r'\([Ff]ig(?:ure)?\.?\s*\d+[A-Za-z]?\)',
        r'\[OCR:.*?\]',
        r'\[Illustration.*?\]',
        r'\[.*?\]',
        r'\{.*?\}',
        r'<.*?>',
        r'\.{4,}',
        r'_{4,}',
        r'[^\w\s.,;:!?\'"—()-]',
        r'\s+',
        r'\n+',
        r'\t+',
        r'(?<!\w)[\/\\](?!\w)'
    ]
    # Common errors that the data in the API texts has due to being OCR text
    replacements = [
        ('“', '"'),
        ('”', '"'),
        ('‘', "'"),
        ('’', "'"),
        ('—', '-'),
        ('–', '-'),
        ('…', '...'),
        ("- ","")
    ]
    for pattern in patterns:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
    for old, new in replacements:
        text = text.replace(old, new)

    text = ' '.join(text.split()).strip()
    return text if text else ""

"""
Procesos de creación del CSV
    Se tiene una para una sola especies para pruebas y otro cuando las pruebas sean exitosas.
* El primero es para pruebas como se mencionó anteriormente, puede recibir un n para saber la cantidad de especies procesar y si no lo recibe solo procesa la primera,(o la posición actual definida)
* El segundo es con todas las especies.
* El tercero recibe la lista de especies que le mande alguna de las dos funciones anteriores y hace llamadas a funciones anteriormente explicadas para ir creando un dataframe con todos esos datos.
"""

def process_species_subset(csv_url, n=None, idioma="Ambas"):
    """
    Procesa un subconjunto de especies:
    - Si species_list está dado: procesa esas especies
    - Si n está dado: procesa las primeras n especies
    - Si ninguno: procesa solo la primera especie (comportamiento original)
    """
    df = read_species_data(csv_url)
    if df.empty:
        return pd.DataFrame()
    if n:
        # Tomar las primeras N especies
        target_species = df["default_name"].unique().tolist()[:n]
    else:
        # Comportamiento original (1 especie)
        target_species = [df.iloc[0]["default_name"]]

    #print(f"Procesando {len(target_species)} especies seleccionadas")
    #commented because the thread function already has a bar for each thread
    return process_species_list(target_species, idioma)

"""
def process_species_range(csv_url, start_index=0, end_index=None, idioma="Ambas"):
    """
"""
    Procesa un subconjunto de especies basado en un rango de índices:
    - start_index: Índice de la primera especie a procesar (inclusivo).
    - end_index: Índice de la última especie a procesar (exclusivo).
      Si es None, se procesan todas las especies desde start_index.
    """
"""
    df = read_species_data(csv_url)
    if df.empty:
        return pd.DataFrame()

    all_species = df["default_name"].unique().tolist()

    # Manejar end_index si es None o mayor al tamaño de la lista
    end_index = min(end_index, len(all_species)) if end_index is not None else len(all_species)

    target_species = all_species[start_index:end_index]

    #print(f"Procesando {len(target_species)} especies en el rango de índices [{start_index}, {end_index})")
    #commented because the thread function already has a bar for each thread
    return process_species_list(target_species, idioma)
"""

#def process_all_species(csv_url, idioma="Ambas"):
#    """Procesa TODAS las especies únicas del CSV."""
#    df = read_species_data(csv_url)
#    if df.empty:
#        return pd.DataFrame()

#    unique_species = df["default_name"].unique().tolist()
#    print(f"Procesando TODAS las {len(unique_species)} especies encontradas")

#    return process_species_list(unique_species, idioma)

def process_species_list(species_list, lenguaje, api_key):
    """Función central para procesar una lista de especies."""
    data_rows = []

    for species in species_list:
        # Pause time so the API KEY doesn´t get banned
        time.sleep(0.35)

        name_metadata = get_name_metadata(species, api_key)
        if not name_metadata:
            continue

        page_ids_preset = conseguirListaPaginas(name_metadata)
        if not page_ids_preset:
            continue
        set_ids = set(page_ids_preset)
        page_ids = list(set_ids)

        num_errores = 0

        for page_id in page_ids:

            if(num_errores == 50): break
            #If a species present a lot of problems it is better to stop trying and go to the next
            page_xml = get_page_metadata(page_id, api_key)
            if not page_xml:
                num_errores+=1
                continue

            try:
                root = ET.fromstring(page_xml)
            except ET.ParseError:
                num_errores+=1
                continue

            page_meta = extract_page_metadata(page_xml)
            ocr_text = root.find('.//OcrText').text if root.find('.//OcrText') is not None else ""

            item_id = root.find('.//ItemID').text if root.find('.//ItemID') is not None else ""
            item_xml = get_item_metadata(item_id, api_key)
            if not item_xml:
                num_errores+=1
                continue

            try:
                root = ET.fromstring(item_xml)
            except ET.ParseError:
                num_errores+=1
                continue

            idioma = root.find('.//Language').text if root.find('.//Language') is not None else ""
            if(lenguaje == "Español"):
              if(not(idioma == "Spanish")):
                continue
            if(lenguaje == "Inglés"):
              if(not(idioma == "English")):
                continue
            if(lenguaje == "Ambas"):
              if(not((idioma == "English")or(idioma == "Spanish"))):
                continue
            item_meta = extract_idItem_metadata(item_xml)

            for para in [p.strip() for p in ocr_text.split("\n\n") if p.strip()]:
                cleaned_para = clean_paragraph(para)
                word_count = len(cleaned_para.split())

                if (word_count >= 50):
                    row = {
                        "species": species,
                        "paragraph": cleaned_para,
                        "page_id": page_id
                    }
                    row.update(page_meta)
                    row.update(item_meta)
                    data_rows.append(row)

    return pd.DataFrame(data_rows)

    