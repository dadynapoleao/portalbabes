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
    match_detailed = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-zA-Z]+)\s+(\d{4})', date_text, re.IGNORECASE)
    if match_detailed:
        day = match_detailed.group(1).zfill(2); month_name = match_detailed.group(2).lower(); year = match_detailed.group(3)
        month_number = month_map.get(month_name)
        if month_number: return f"{year}/{month_number}/{day}"
    match_day_month_year = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\s+(\d{4})', date_text, re.IGNORECASE)
    if match_day_month_year:
        day = match_day_month_year.group(1).zfill(2); month_name = match_day_month_year.group(2).lower(); year = match_day_month_year.group(3)
        month_number = month_map.get(month_name)
        if month_number: return f"{year}/{month_number}/{day}"
    app.logger.debug(f"Could not parse date format with known patterns: {date_text}")
    return date_text

def extract_country(birthplace_text):
    if not birthplace_text:
        app.logger.debug("extract_country: Input is None or empty, returning None")
        return None
    app.logger.debug(f"extract_country: Original input: '{birthplace_text}'")
    text_cleaned = re.sub(r'\s*\([^)]*\)$', '', birthplace_text).strip()
    app.logger.debug(f"extract_country: After removing final parentheses: '{text_cleaned}'")
    source_for_split = text_cleaned if text_cleaned else birthplace_text
    parts = source_for_split.split(',')
    app.logger.debug(f"extract_country: Parts after split from '{source_for_split}': {parts}")
    if not parts:
        app.logger.warning(f"extract_country: No parts after split for '{source_for_split}'. Returning None.")
        return None
    country_candidate = parts[-1].strip()
    app.logger.debug(f"extract_country: Candidate (last part stripped): '{country_candidate}'")
    if not country_candidate and len(parts) > 1:
        app.logger.debug("extract_country: Last part was empty, trying second to last part.")
        country_candidate = parts[-2].strip()
        app.logger.debug(f"extract_country: Second to last part candidate: '{country_candidate}'")
    if not country_candidate:
        app.logger.warning(f"extract_country: Could not determine country from '{birthplace_text}'. Candidate is empty. Returning original cleaned text if available, or original input.")
        return text_cleaned if text_cleaned else birthplace_text 
    app.logger.info(f"extract_country: Extracted country: '{country_candidate}' from input '{birthplace_text}'")
    return country_candidate

def extract_start_year(active_text):
    if not active_text: return None
    match = re.search(r'^(\d{4})\s*-\s*present', active_text)
    if match: return match.group(1)
    match_year_only = re.search(r'^(\d{4})', active_text)
    if match_year_only: return match_year_only.group(1)
    return None

# --- Função para Parsear o HTML ---
def parse_html_data(soup):
    data = {}; temp_data = {}
    app.logger.info("Starting HTML parsing using 'biolist' structure...")
    try:
        biolist = soup.find('ul', id='biolist')
        if not biolist:
            app.logger.warning("Could not find <ul id='biolist'>. Data extraction might fail.")
            return data

        label_map = {
            "Age:": "age_raw", "Born:": "born", "Birthplace:": "birthplace",
            "Ethnicity:": "ethnicity", "Sexuality:": "sexuality", "Profession:": "profession",
            "Hair color:": "hair_color", "Eye color:": "eye_color", "Height:": "height",
            "Weight:": "weight", "Body type:": "body_type", "Measurements:": "measurements_raw",
            "Bra/cup size:": "bra_cup_size", "Boobs:": "boobs_type", "Pubic hair:": "pubic_hair",
            "Years active:": "years_active", "Tattoos:": "tattoos", "Piercings:": "piercings",
            "Instagram follower count:": "instagram_followers"
            # Adicione outros labels aqui se necessário, ex: "Country:": "birthplace",
        }

        for li_item in biolist.find_all('li', recursive=False):
            label_span = li_item.find('span', class_='label')
            label_text_from_span = ""
            raw_value = "" # Inicializa raw_value

            if label_span:
                label_text_from_span = label_span.get_text(strip=True)
            else:
                # Se não encontrar <span class="label">, tenta uma abordagem mais genérica
                # Pega o primeiro texto forte ou bold dentro do <li> como possível label
                strong_tag = li_item.find(['strong', 'b'])
                if strong_tag:
                    possible_label_text = strong_tag.get_text(strip=True)
                    # Verifica se esse possível label termina com ':' e está no map
                    if possible_label_text.endswith(':') and possible_label_text in label_map:
                        label_text_from_span = possible_label_text
                        app.logger.info(f"Found label '{label_text_from_span}' using strong/b tag fallback.")
                        # Tenta pegar o valor após o strong/b tag
                        value_parts_fallback = []
                        for elem in strong_tag.next_siblings:
                            if elem.name == 'a':
                                link_text = elem.get_text(strip=True)
                                if link_text: value_parts_fallback.append(link_text)
                            elif isinstance(elem, str):
                                text_content = elem.strip()
                                if text_content and text_content != ',': value_parts_fallback.append(text_content)
                        raw_value = " ".join(value_parts_fallback).strip()
                        raw_value = re.sub(r'\s*,\s*', ', ', raw_value).strip(' ,')
                    else:
                        app.logger.debug(f"Skipping li_item, strong/b tag content '{possible_label_text}' not a mapped label: {str(li_item)[:150]}...")
                        continue # Pula para o próximo li_item
                else:
                    app.logger.warning(f"MISSING_LABEL_SPAN_AND_FALLBACK: Could not find label in li_item: {str(li_item)[:150]}")
                    continue # Pula para o próximo li_item

            # Se o label foi encontrado (seja por span.label ou pelo fallback)
            if label_text_from_span and label_text_from_span in label_map:
                data_key = label_map[label_text_from_span]
                
                # Se o raw_value não foi preenchido pelo fallback, usa a lógica original
                if not raw_value and label_span: # label_span deve existir para esta lógica
                    value_parts = []
                    for elem in label_span.next_siblings:
                        if elem.name == 'a':
                            link_text = elem.get_text(strip=True)
                            if link_text: value_parts.append(link_text)
                        elif isinstance(elem, str):
                            text_content = elem.strip()
                            if text_content and text_content != ',': value_parts.append(text_content)
                    raw_value = " ".join(value_parts).strip()
                    raw_value = re.sub(r'\s*,\s*', ', ', raw_value).strip(' ,')

                app.logger.info(f"Extraction for label '{label_text_from_span}' (key: '{data_key}'). Resulting Raw Value: '{raw_value}'")

                if raw_value:
                    temp_data[data_key] = raw_value
            elif label_text_from_span: # Label foi encontrado mas não está no map
                app.logger.debug(f"Label '{label_text_from_span}' found in HTML but not in label_map.")
        
        # Processa os valores de temp_data para o dicionário final 'data'
        if 'born' in temp_data: data['born'] = format_babepedia_date(temp_data['born'])
        if 'birthplace' in temp_data: data['birthplace'] = extract_country(temp_data['birthplace'])
        if 'height' in temp_data: data['height'] = extract_cm(temp_data['height'])
        if 'weight' in temp_data: data['weight'] = extract_kg(temp_data['weight'])
        if 'years_active' in temp_data: data['years_active'] = extract_start_year(temp_data['years_active'])

        if 'measurements_raw' in temp_data:
            cleaned_value = temp_data['measurements_raw'].split('Bra/cup size:')[0].strip()
            parts = cleaned_value.split('-'); boobs_num, waist_num, ass_num = None, None, None
            if len(parts) == 3:
                boobs_num = extract_first_number(parts[0]); waist_num = extract_first_number(parts[1]); ass_num = extract_first_number(parts[2])
                if boobs_num: data['Boobs'] = boobs_num
                if waist_num: data['Waist'] = waist_num
                if ass_num: data['Ass'] = ass_num
                if boobs_num and waist_num and ass_num: data['measurements'] = f"{boobs_num}-{waist_num}-{ass_num}"
                else: data['measurements'] = cleaned_value 
            else: data['measurements'] = cleaned_value

        direct_assignment_keys = [
            'age_raw', 'ethnicity', 'sexuality', 'profession', 'hair_color', 'eye_color', 
            'body_type', 'bra_cup_size', 'boobs_type', 'pubic_hair', 
            'tattoos', 'piercings', 'instagram_followers'
        ]
        for key in direct_assignment_keys:
            if key in temp_data: data[key] = temp_data[key]

    except Exception as e:
        app.logger.error(f"Error during HTML parsing: {e}", exc_info=True)

    data_cleaned = {k: v for k, v in data.items() if v is not None and str(v).strip() != ''}
    app.logger.info(f"Finished parsing. Final data to be returned (cleaned): {data_cleaned}")
    return data_cleaned
    
# --- Função Principal de Scraping ---
def scrape_babepedia_data(babe_name_formatted):
    url = f'https://www.babepedia.com/babe/{babe_name_formatted}'
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
             app.logger.warning(f"Scraping for {babe_name_formatted} completed, but no specific data fields were extracted.")
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
        app.logger.info(f"API Successfully scraped data for {babe_name}. Returning JSON: {scraped_data}")
        return jsonify(scraped_data)

# --- Para rodar localmente ---
# if __name__ == '__main__':
#     # Para ver logs de DEBUG localmente, descomente a linha abaixo e a configuração de logging.basicConfig
#     # logging.basicConfig(level=logging.DEBUG) 
#     app.run(debug=True, port=os.environ.get("PORT", 5001))
