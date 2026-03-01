import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
import re

app = Flask(__name__)
CORS(app)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def extract_with_regex(pattern, text, group=1):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(group).strip() if match else None

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Falta nome"}), 400
    
    # Formata nome para URL (Lilith Grace -> Lilith_Grace)
    name_url = name.replace(" ", "_")
    url = f'https://www.babepedia.com/babe/{name_url}'
    
    try:
        response = scraper.get(url, timeout=15)
        # Pegamos o texto bruto da página, ignorando tags HTML
        html_text = response.text
        
        data = {}
        
        # 1. Extração de Data de Nascimento (Busca: Born: [texto] Years active)
        born_raw = extract_with_regex(r'Born:</span>(.*?)(?:Years active|Birthplace)', html_text)
        if not born_raw: # Tenta sem a tag span
             born_raw = extract_with_regex(r'Born:(.*?)(?:Years active|Birthplace)', html_text)
        
        if born_raw:
            # Limpa HTML do valor
            born_raw = re.sub('<[^<]+?>', '', born_raw).strip()
            # Converte data para 1994/02/24
            months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
            m = re.search(r'(\d{1,2}).+?([a-zA-Z]+)\s+(\d{4})', born_raw)
            if m:
                data['born'] = f"{m.group(3)}/{months.get(m.group(2).lower(), '01')}/{m.group(1).zfill(2)}"

        # 2. Extração de Medidas (Busca: Measurements: [texto] Bra)
        meas_raw = extract_with_regex(r'Measurements:</span>(.*?)(?:Bra|Boobs|Body)', html_text)
        if meas_raw:
            meas_raw = re.sub('<[^<]+?>', '', meas_raw)
            nums = re.findall(r'\d+', meas_raw)
            if len(nums) >= 3:
                data['measurements'] = f"{nums[0]}-{nums[1]}-{nums[2]}"

        # 3. Altura (Busca número antes de cm)
        height_match = re.search(r'\(or\s+(\d+)\s*cm\)', html_text)
        if height_match:
            data['height'] = height_match.group(1)

        # 4. Peso (Busca número antes de kg)
        weight_match = re.search(r'\(or\s+(\d+)\s*kg\)', html_text)
        if weight_match:
            data['weight'] = weight_match.group(1)

        # 5. Etnia e País
        data['ethnicity'] = extract_with_regex(r'Ethnicity:</span>\s*<a[^>]*>(.*?)</a>', html_text)
        data['birthplace'] = extract_with_regex(r'Birthplace:</span>\s*(.*?)(?:Nationality|<)', html_text)
        if data['birthplace']:
            data['birthplace'] = re.sub('<[^<]+?>', '', data['birthplace']).split(',')[-1].strip()

        # 6. Cabelo e Olhos
        data['hair_color'] = extract_with_regex(r'Hair color:</span>\s*(.*?)(?:<)', html_text)
        data['eye_color'] = extract_with_regex(r'Eye color:</span>\s*(.*?)(?:<)', html_text)

        data['source_url'] = url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
