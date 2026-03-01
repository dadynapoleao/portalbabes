import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import logging
import re

# --- Configuração do Flask App ---
app = Flask(__name__)
CORS(app)

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Inicialização do Scraper ---
# Criamos o scraper aqui para evitar bloqueios
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

# --- Funções Auxiliares (Mantidas do seu código original) ---
def extract_first_number(text):
    if not text: return None
    match = re.search(r'\d+', str(text))
    return match.group(0) if match else None

def extract_cm(height_text):
    if not height_text: return None
    match = re.search(r'\((\d+)\s*cm\)', height_text)
    if match: return match.group(1)
    match_direct = re.search(r'(\d+)\s*cm', height_text)
    if match_direct: return match_direct.group(1)
    return None

def extract_kg(weight_text):
    if not weight_text: return None
    match = re.search(r'\((\d+)\s*kg\)', weight_text)
    if match: return match.group(1)
    return None

def format_babepedia_date(date_text):
    if not date_text: return None
    month_map = {'january': '01', 'february': '02', 'march': '03', 'april': '04', 'may': '05', 'june': '06', 'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12'}
    match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\s+(\d{4})', date_text, re.IGNORECASE)
    if match:
        day = match.group(1).zfill(2); month = month_map.get(match.group(2).lower()); year = match.group(3)
        if month: return f"{year}/{month}/{day}"
    return date_text

def extract_country(birthplace_text):
    if not birthplace_text: return None
    parts = [p.strip() for p in birthplace_text.split(',') if p.strip()]
    return parts[-1] if parts else None

def extract_start_year(active_text):
    if not active_text: return None
    match = re.search(r'(\d{4})', active_text)
    return match.group(1) if match else None

# --- Lógica de Parsing ---
def parse_html_data(soup):
    data = {}
    temp_data = {}
    try:
        biolist = soup.find('ul', id='biolist')
        if not biolist: return data

        label_map = {
            "Born:": "born_raw", "Birthplace:": "birthplace", "Ethnicity:": "ethnicity",
            "Hair color:": "hair_color", "Eye color:": "eye_color", "Height:": "height_raw",
            "Weight:": "weight_raw", "Body type:": "body_type", "Measurements:": "measurements_raw",
            "Years active:": "years_active_raw"
        }

        for li in biolist.find_all('li', recursive=False):
            label_span = li.find('span', class_='label') or li.find(['strong', 'b'])
            if label_span:
                lbl = label_span.get_text().strip()
                if lbl in label_map:
                    val = li.get_text().replace(lbl, '').strip()
                    temp_data[label_map[lbl]] = val

        if 'born_raw' in temp_data: data['born'] = format_babepedia_date(temp_data['born_raw'])
        if 'birthplace' in temp_data: data['birthplace'] = extract_country(temp_data['birthplace'])
        if 'height_raw' in temp_data: data['height'] = extract_cm(temp_data['height_raw'])
        if 'weight_raw' in temp_data: data['weight'] = extract_kg(temp_data['weight_raw'])
        if 'years_active_raw' in temp_data: data['years_active'] = extract_start_year(temp_data['years_active_raw'])
        
        if 'measurements_raw' in temp_data:
            m = temp_data['measurements_raw'].split('-')
            if len(m) == 3:
                data['Boobs'] = extract_first_number(m[0])
                data['Waist'] = extract_first_number(m[1])
                data['Ass'] = extract_first_number(m[2])
                data['measurements'] = f"{data['Boobs']}-{data['Waist']}-{data['Ass']}"

        for k in ['ethnicity', 'hair_color', 'eye_color', 'body_type']:
            if k in temp_data: data[k] = temp_data[k]

    except Exception as e:
        logger.error(f"Erro no parse: {e}")
    return data

# --- Endpoints ---
@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Nome obrigatorio"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    try:
        # Usando cloudscraper para evitar erro 403
        response = scraper.get(url, timeout=15)
        if response.status_code == 404:
            return jsonify({"error": "Atriz nao encontrada"}), 404
            
        soup = BeautifulSoup(response.content, 'html.parser')
        result = parse_html_data(soup)
        result['source_url'] = url
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
