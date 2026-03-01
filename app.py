import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

# Configura o scraper para simular um navegador real
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def format_date(text):
    # Converte "Thursday 24th of February 1994" para "1994/02/24"
    months = {
        "january":"01", "february":"02", "march":"03", "april":"04", "may":"05", "june":"06",
        "july":"07", "august":"08", "september":"09", "october":"10", "november":"11", "december":"12"
    }
    match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-zA-Z]+)\s+(\d{4})', text, re.I)
    if match:
        day = match.group(1).zfill(2)
        month = months.get(match.group(2).lower(), "01")
        year = match.group(3)
        return f"{year}/{month}/{day}"
    return text

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Nome obrigatorio"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        if response.status_code == 404: return jsonify({"error": "Nao encontrado"}), 404
        
        soup = BeautifulSoup(response.content, 'html.parser')
        data = {}
        biolist = soup.find('ul', id='biolist')
        
        if biolist:
            for li in biolist.find_all('li'):
                label_tag = li.find('span', class_='label') or li.find('strong')
                if not label_tag: continue
                
                label = label_tag.get_text().lower().strip()
                # Pega o valor limpando o label
                val = li.get_text().replace(label_tag.get_text(), "").strip()

                if "born:" in label:
                    data['born'] = format_date(val)
                elif "birthplace:" in label:
                    data['birthplace'] = val.split(',')[-1].strip()
                elif "ethnicity:" in label:
                    data['ethnicity'] = val
                elif "height:" in label:
                    # Extrai o "160" de "5'3" (or 160 cm)"
                    h = re.search(r'(\d+)\s*cm', val)
                    if h: data['height'] = h.group(1)
                elif "weight:" in label:
                    # Extrai o "57" de "125 lbs (or 57 kg)"
                    w = re.search(r'(\d+)\s*kg', val)
                    if w: data['weight'] = w.group(1)
                elif "measurements:" in label:
                    # Limpa medidas como "36F-24-36" para "36-24-36"
                    m = re.findall(r'\d+', val)
                    if len(m) >= 3: data['measurements'] = f"{m[0]}-{m[1]}-{m[2]}"
                elif "years active:" in label:
                    y = re.search(r'(\d{4})', val)
                    if y: data['years_active'] = y.group(1)
                elif "hair color:" in label:
                    data['hair_color'] = val
                elif "eye color:" in label:
                    data['eye_color'] = val
                elif "body type:" in label:
                    data['body_type'] = val

        data['source_url'] = url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
