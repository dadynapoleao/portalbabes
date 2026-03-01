import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def extract_val(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Nome obrigatorio"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        # Transforma o HTML em texto puro e limpo
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove scripts e estilos antes de pegar o texto
        for script in soup(["script", "style"]):
            script.extract()
            
        page_text = soup.get_text(separator=" ")
        # Remove espaços duplos e quebras de linha excessivas
        page_text = " ".join(page_text.split())
        
        data = {}
        
        # --- BUSCA NO TEXTO PURO ---
        
        # 1. Born (Pega o texto entre 'Born:' e 'Years active' ou 'Birthplace')
        born_raw = extract_val(r'Born:\s*(.*?)(?=\s+Years active|\s+Birthplace|\s+Nationality|\s+Ethnicity)', page_text)
        if born_raw:
            months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
            m = re.search(r'(\d{1,2}).+?([a-zA-Z]+)\s+(\d{4})', born_raw)
            if m:
                data['born'] = f"{m.group(3)}/{months.get(m.group(2).lower(), '01')}/{m.group(1).zfill(2)}"

        # 2. Measurements
        meas_raw = extract_val(r'Measurements:\s*([\d\w]+-[\d\w]+-[\d\w]+)', page_text)
        if meas_raw:
            nums = re.findall(r'\d+', meas_raw)
            if len(nums) >= 3: data['measurements'] = f"{nums[0]}-{nums[1]}-{nums[2]}"

        # 3. Altura e Peso
        h = re.search(r'\(or\s+(\d+)\s*cm\)', page_text)
        if h: data['height'] = h.group(1)
        
        w = re.search(r'\(or\s+(\d+)\s*kg\)', page_text)
        if w: data['weight'] = w.group(1)

        # 4. Outros campos
        data['ethnicity'] = extract_val(r'Ethnicity:\s*(.*?)(?=\s+Profession|\s+Sexuality|\s+Body)', page_text)
        data['birthplace'] = extract_val(r'Birthplace:\s*(.*?)(?=\s+Nationality|\s+Ethnicity|\s+Born)', page_text)
        if data['birthplace']: data['birthplace'] = data['birthplace'].split(',')[-1].strip()
        
        data['hair_color'] = extract_val(r'Hair color:\s*(.*?)(?=\s+Eye color)', page_text)
        data['eye_color'] = extract_val(r'Eye color:\s*(.*?)(?=\s+Height)', page_text)
        data['years_active'] = extract_val(r'Years active:\s*(\d{4})', page_text)

        data['source_url'] = url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
