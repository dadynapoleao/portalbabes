# --- Imports ---
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import logging
import re

# --- Configuração do Flask App e CORS ---
app = Flask(__name__)
CORS(app)

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO)
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers.extend(gunicorn_logger.handlers)
app.logger.setLevel(logging.INFO)

# --- Funções Auxiliares de Extração/Formatação ---
def extract_first_number(text):
    if not text: return None
    match = re.search(r'\d+', str(text))
    return match.group(0) if match else None

def extract_cm(height_text):
    if not height_text: return None
    match_paren = re.search(r'\((\d+)\s*cm\)', height_text)
    if match_paren: return match_paren.group(1)
    match_direct = re.search(r'(\d+)\s*cm', height_text)
    if match_direct: return match_direct.group(1)
    match_num_only = re.fullmatch(r'(\d{3})', height_text)
    if match_num_only and 100 < int(match_num_only.group(1)) < 250: return match_num_only.group(1)
    return None

def extract_kg(weight_text):
    if not weight_text: return None
    match_paren = re.search(r'\((\d+)\s*kg\)', weight_text)
    if match_paren: return match_paren.group(1)
    match_direct = re.search(r'(\d+)\s*kg', weight_text)
    if match_direct: return match_direct.group(1)
    match_num_only = re.fullmatch(r'(\d{2,3})', weight_text)
    if match_num_only and 30 < int(match_num_only.group(1)) < 200: return match_num_only.group(1)
    return None

def format_babepedia_date(date_text):
    if not date_text: return None
    month_map = {'january': '01', 'february': '02', 'march': '03', 'april': '04', 'may': '05', 'june': '06', 'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12'}
    # Prioritize format "Day(st/nd/rd/th) of Month Year"
    match_detailed = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-zA-Z]+)\s+(\d{4})', date_text, re.IGNORECASE)
    if match_detailed:
        day = match_detailed.group(1).zfill(2); month_name = match_detailed.group(2).lower(); year = match_detailed.group(3)
        month_number = month_map.get(month_name)
        if month_number: return f"{year}/{month_number}/{day}"
    # Fallback to "Day Month Year"
    match_day_month_year = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\s+(\d{4})', date_text, re.IGNORECASE)
    if match_day_month_year:
        day = match_day_month_year.group(1).zfill(2); month_name = match_day_month_year.group(2).lower(); year = match_day_month_year.group(3)
        month_number = month_map.get(month_name)
        if month_number: return f"{year}/{month_number}/{day}"
    app.logger.debug(f"Could not parse date format with known patterns: {date_text}")
    return date_text # Return original if no known pattern matches

def extract_country(birthplace_text):
    if not birthplace_text:
        app.logger.debug("extract_country: Input is None or empty, returning None")
        return None
    app.logger.debug(f"extract_country: Original input: '{birthplace_text}'")

    # Lista simplificada de abreviações de estados dos EUA e alguns nomes de províncias/regiões comuns
    # Esta lista ajuda a identificar partes que NÃO são o país final.
    known_states_provinces_regions = [
        # EUA (abreviações comuns)
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "D.C.", "DC",
        # EUA (nomes completos comuns)
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
        # Canadá (exemplos de províncias)
        "Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba",
        "Saskatchewan", "Nova Scotia", "New Brunswick",
        "Newfoundland and Labrador", "Prince Edward Island", "BC", "AB", "ON", "QC",
        # UK (partes constituintes)
        "England", "Scotland", "Wales", "Northern Ireland",
        # Outras regiões conhecidas
        "Donetsk Oblast" # Exemplo específico
    ]
    known_states_provinces_normalized = {s.lower().strip() for s in known_states_provinces_regions}

    text_cleaned = re.sub(r'\s*\([^)]*\)$', '', birthplace_text).strip() # Remove (info) no final
    app.logger.debug(f"extract_country: After removing final parentheses: '{text_cleaned}'")

    source_for_split = text_cleaned if text_cleaned else birthplace_text
    # Divide por vírgula, remove espaços de cada parte, e filtra partes vazias
    parts = [p.strip() for p in source_for_split.split(',') if p.strip()]
    app.logger.debug(f"extract_country: Parts after split and strip: {parts}")

    if not parts:
        app.logger.warning(f"extract_country: No valid parts after split for '{source_for_split}'. Returning original cleaned text if available, or original input.")
        return text_cleaned if text_cleaned else birthplace_text

    # Itera pelas partes de trás para frente
    for i in range(len(parts) - 1, -1, -1):
        candidate_part = parts[i]
        app.logger.debug(f"extract_country: Checking candidate part (from right to left): '{candidate_part}'")
        # Se a parte candidata NÃO estiver na lista de estados/províncias/regiões conhecidos
        # E tiver um comprimento razoável (improvável que um país seja 1 ou 2 caracteres)
        if candidate_part.lower() not in known_states_provinces_normalized and len(candidate_part) > 2:
            app.logger.info(f"extract_country: Extracted country as '{candidate_part}' (not in known states/provinces and len > 2) from input '{birthplace_text}'")
            return candidate_part
        
        # Caso especial: se depois de remover estados/províncias, sobrou apenas uma parte, essa deve ser o país
        # Ou se a string original só tinha uma parte (ex: "France")
        if len(parts) == 1: # Se havia apenas uma parte para começar
             app.logger.info(f"extract_country: Extracted country as '{candidate_part}' (single part input) from input '{birthplace_text}'")
             return candidate_part


    # Fallback: Se todas as partes foram consideradas estados/províncias ou a lógica acima não funcionou,
    # retorna a última parte como tentativa.
    # Isso pode acontecer se o "país" for algo como "California" e ele estiver na lista de estados.
    # Ou se a lista de estados/províncias for muito agressiva.
    fallback_country = parts[-1] # A última parte restante
    app.logger.warning(f"extract_country: Could not definitively identify country via main logic. Defaulting to last part: '{fallback_country}' from input '{birthplace_text}'")
    return fallback_country


def extract_start_year(active_text):
    if not active_text: return None
    match = re.search(r'^(\d{4})\s*-\s*present', active_text, re.IGNORECASE)
    if match: return match.group(1)
    match_year_only = re.search(r'^(\d{4})', active_text)
    if match_year_only: return match_year_only.group(1)
    return None

# --- Função para Parsear o HTML ---
def parse_html_data(soup):
    data = {}
    temp_data = {}
    app.logger.info("Starting HTML parsing using 'biolist' structure...")
    try:
        biolist = soup.find('ul', id='biolist')
        if not biolist:
            app.logger.warning("Could not find <ul id='biolist'>. Data extraction might fail.")
            return data

        label_map = {
            "Age:": "age_raw",
            "Born:": "born_raw",
            "Birthplace:": "birthplace_temp_val", # Chave para "Birthplace:" com :
            "Birthplace": "birthplace_temp_val",  # Chave para "Birthplace" sem :
            "Ethnicity:": "ethnicity",
            "Sexuality:": "sexuality",
            "Profession:": "profession",
            "Hair color:": "hair_color",
            "Eye color:": "eye_color",
            "Height:": "height_raw",
            "Weight:": "weight_raw",
            "Body type:": "body_type",
            "Measurements:": "measurements_raw",
            "Bra/cup size:": "bra_cup_size",
            "Boobs:": "boobs_type",
            "Pubic hair:": "pubic_hair",
            "Years active:": "years_active_raw",
            "Tattoos:": "tattoos",
            "Piercings:": "piercings",
            "Instagram follower count:": "instagram_followers"
        }
        
        normalized_label_map = {re.sub(r'\s+', ' ', k.lower()).strip(): v for k, v in label_map.items()}

        for li_item in biolist.find_all('li', recursive=False):
            app.logger.debug(f"Processing li_item: {str(li_item)[:200]}")

            label_span = li_item.find('span', class_='label')
            label_text_from_html = ""
            processed_label_for_map = ""
            current_label_element = None

            if label_span:
                current_label_element = label_span
                label_text_from_html = label_span.get_text() 
                processed_label_for_map = re.sub(r'\s+', ' ', label_text_from_html.lower()).strip()
                app.logger.info(f"LABEL_SPAN_FOUND: Raw text='{label_text_from_html}', Processed for map check='{processed_label_for_map}'")
            else: 
                strong_tag = li_item.find(['strong', 'b'])
                if strong_tag:
                    current_label_element = strong_tag
                    label_text_from_html = strong_tag.get_text()
                    processed_label_for_map = re.sub(r'\s+', ' ', label_text_from_html.lower()).strip()
                    app.logger.info(f"STRONG_B_FALLBACK: Raw text='{label_text_from_html}', Processed for map check='{processed_label_for_map}'")
                else:
                    app.logger.warning(f"NO_LABEL_ELEMENT_FOUND in li_item: {str(li_item)[:150]}")
                    continue
            
            if processed_label_for_map in normalized_label_map:
                data_key_for_temp = normalized_label_map[processed_label_for_map]
                
                value_parts = []
                if current_label_element:
                    for elem in current_label_element.next_siblings:
                        if elem.name == 'a':
                            link_text = elem.get_text(strip=True)
                            if link_text: value_parts.append(link_text)
                        elif isinstance(elem, str):
                            text_content = elem.strip()
                            if text_content and text_content != ',': value_parts.append(text_content)
                
                raw_value = " ".join(value_parts).strip()
                raw_value = re.sub(r'\s*,\s*', ', ', raw_value).strip(' ,')

                app.logger.info(f"Extraction for MAPPED_LABEL '{label_text_from_html.strip()}' (key for temp_data: '{data_key_for_temp}'). Value Parts: {value_parts}. Resulting Raw Value: '{raw_value}'")

                if raw_value:
                    temp_data[data_key_for_temp] = raw_value
            elif label_text_from_html.strip():
                app.logger.debug(f"Label text '{label_text_from_html.strip()}' found in HTML but not recognized or mapped.")
        
        if 'born_raw' in temp_data: data['born'] = format_babepedia_date(temp_data['born_raw'])
        if 'birthplace_temp_val' in temp_data: 
            data['birthplace'] = extract_country(temp_data['birthplace_temp_val'])
        if 'height_raw' in temp_data: data['height'] = extract_cm(temp_data['height_raw'])
        if 'weight_raw' in temp_data: data['weight'] = extract_kg(temp_data['weight_raw'])
        if 'years_active_raw' in temp_data: data['years_active'] = extract_start_year(temp_data['years_active_raw'])

        if 'measurements_raw' in temp_data:
            cleaned_value = temp_data['measurements_raw'].split('Bra/cup size:')[0].strip()
            parts = cleaned_value.split('-')
            boobs_num, waist_num, ass_num = None, None, None
            if len(parts) == 3:
                boobs_num = extract_first_number(parts[0]); waist_num = extract_first_number(parts[1]); ass_num = extract_first_number(parts[2])
                if boobs_num: data['Boobs'] = boobs_num
                if waist_num: data['Waist'] = waist_num
                if ass_num: data['Ass'] = ass_num
                if boobs_num and waist_num and ass_num: data['measurements'] = f"{boobs_num}-{waist_num}-{ass_num}"
                else: data['measurements'] = cleaned_value 
            else: data['measurements'] = cleaned_value

        direct_assignment_keys_from_temp = [
            'age_raw', 'ethnicity', 'sexuality', 'profession', 'hair_color', 
            'eye_color', 'body_type', 'bra_cup_size', 'boobs_type', 
            'pubic_hair', 'tattoos', 'piercings', 'instagram_followers'
        ]
        for temp_key in direct_assignment_keys_from_temp:
            if temp_key in temp_data:
                final_key = temp_key.replace('_raw', '')
                data[final_key] = temp_data[temp_key]

    except Exception as e:
        app.logger.error(f"Error during HTML parsing: {e}", exc_info=True)

    data_cleaned = {k: v for k, v in data.items() if v is not None and str(v).strip() != ''}
    app.logger.info(f"Finished parsing. Final data to be returned (cleaned): {data_cleaned}")
    return data_cleaned
    
# --- Função Principal de Scraping ---
def scrape_babepedia_data(babe_name_formatted):
    babe_name_for_url = babe_name_formatted
    url = f'https://www.babepedia.com/babe/{babe_name_for_url}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    scraped_info = {}
    try:
        app.logger.info(f"Requesting URL: {url}")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        app.logger.info(f"Request successful (Status: {response.status_code}). Parsing content...")
        soup = BeautifulSoup(response.content, 'html.parser')
        scraped_info = parse_html_data(soup)
        scraped_info['searched_name'] = babe_name_formatted
        scraped_info['source_url'] = url
        useful_keys = [k for k in scraped_info if k not in ['searched_name', 'source_url']]
        if not useful_keys and "error" not in scraped_info :
             app.logger.warning(f"Scraping for {babe_name_formatted} completed, but no specific data fields were extracted beyond default info.")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code; app.logger.error(f"HTTP Error {status_code} for {url}: {e}")
        scraped_info = {"error": f"Atriz não encontrada ou erro na página (Status: {status_code})", "status_code": status_code}
    except requests.exceptions.Timeout:
        app.logger.error(f"Request timed out for {url}")
        scraped_info = {"error": "Timeout ao acessar Babepedia", "status_code": 408}
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request failed for {url}: {e}")
        scraped_info = {"error": f"Falha na conexão com Babepedia: {e}", "status_code": 503}
    except Exception as e:
        app.logger.error(f"Unexpected error during scraping for {babe_name_formatted}: {e}", exc_info=True)
        scraped_info = {"error": "Erro inesperado no servidor durante o scraping.", "status_code": 500}
    return scraped_info

# --- Endpoint da API (/scrape_babe) ---
@app.route('/scrape_babe')
def scrape_babe_api():
    babe_name = request.args.get('name')
    app.logger.info(f"Received API request for name: {babe_name}")
    if not babe_name:
        app.logger.warning("API Request received without 'name' parameter.")
        return jsonify({"error": "Parâmetro 'name' é obrigatório"}), 400
    scraped_data = scrape_babepedia_data(babe_name)
    if "error" in scraped_data:
        status = scraped_data.get("status_code", 500)
        app.logger.info(f"API Returning error for {babe_name}: Status {status}, Message: {scraped_data['error']}")
        return jsonify(scraped_data), status
    else:
        app.logger.info(f"API Successfully scraped data for {babe_name}.")
        app.logger.debug(f"API Returning JSON for {babe_name}: {scraped_data}")
        return jsonify(scraped_data)

# --- Para rodar localmente ---
# if __name__ == '__main__':
#     # logging.getLogger().setLevel(logging.DEBUG) 
#     # app.logger.setLevel(logging.DEBUG)
#     app.run(debug=True, port=os.environ.get("PORT", 5001))
