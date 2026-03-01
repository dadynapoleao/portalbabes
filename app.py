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

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Falta nome"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        text = response.text
        
        # Limpa o HTML para facilitar a busca no texto puro
        clean_text = re.sub(r'<[^>]+>', ' ', text)
        clean_text = " ".join(clean_text.split())

        data = {}
        
        # 1. Born
        born_match = re.search(r'Born:\s*([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}|[a-zA-Z]+\s+\d{1,2}\s+\d{4}|\d{1,2}\s+of\s+[a-zA-Z]+\s+\d{4})', clean_text, re.I)
        if born_match:
            raw_date = born_match.group(1)
            months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
            m = re.search(r'(\d{1,2}).+?([a-zA-Z]+)\s+(\d{4})|([a-zA-Z]+)\s+(\d{1,2}).+?(\d{4})', raw_date)
            if m:
                if m.group(1): # Formato: 24 of February 1994
                    data['born'] = f"{m.group(3)}/{months.get(m.group(2).lower(), '01')}/{m.group(1).zfill(2)}"
                else: # Formato: February 24, 1994
                    data['born'] = f"{m.group(6)}/{months.get(m.group(4).lower(), '01')}/{m.group(5).zfill(2)}"

        # 2. Measurements
        m_match = re.search(r'Measurements:\s*(\d+[a-zA-Z]?-\d+-\d+)', clean_text, re.I)
        if m_match:
            nums = re.findall(r'\d+', m_match.group(1))
            if len(nums) >= 3: data['measurements'] = f"{nums[0]}-{nums[1]}-{nums[2]}"

        # 3. Altura (cm) e Peso (kg)
        h_match = re.search(r'(\d+)\s*cm', clean_text)
        if h_match: data['height'] = h_match.group(1)
        
        w_match = re.search(r'(\d+)\s*kg', clean_text)
        if w_match: data['weight'] = w_match.group(1)

        # 4. Outros
        data['ethnicity'] = (re.search(r'Ethnicity:\s*([a-zA-Z\s]+)', clean_text, re.I) or [None, None])[1]
        data['hair_color'] = (re.search(r'Hair color:\s*([a-zA-Z\s]+)', clean_text, re.I) or [None, None])[1]
        data['eye_color'] = (re.search(r'Eye color:\s*([a-zA-Z\s]+)', clean_text, re.I) or [None, None])[1]
        data['years_active'] = (re.search(r'Years active:\s*(\d{4})', clean_text, re.I) or [None, None])[1]

        data['source_url'] = url
        return jsonify({k: v.strip() if isinstance(v, str) else v for k, v in data.items()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
