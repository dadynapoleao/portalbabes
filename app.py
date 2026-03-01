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

def format_date(text):
    months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
    # Procura "24th of February 1994" ou "February 24, 1994"
    match = re.search(r'(\d{1,2})?.+?([a-zA-Z]+)\s+(\d{1,2})?.+?(\d{4})', text)
    if match:
        # Tenta identificar qual grupo é o dia e qual é o mês
        year = match.group(4)
        month_name = match.group(2).lower()
        day = (match.group(1) or match.group(3) or "01").zfill(2)
        return f"{year}/{months.get(month_name, '01')}/{day}"
    return text

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Falta nome"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Pega todo o texto das listas da página
        all_li = soup.find_all('li')
        data = {}
        
        for li in all_li:
            text = li.get_text(separator=" ").strip()
            
            if "Born:" in text:
                data['born'] = format_date(text.replace("Born:", "").strip())
            elif "Birthplace:" in text:
                data['birthplace'] = text.replace("Birthplace:", "").strip().split(',')[-1].strip()
            elif "Height:" in text:
                h = re.search(r'(\d+)\s*cm', text)
                if h: data['height'] = h.group(1)
            elif "Weight:" in text:
                w = re.search(r'(\d+)\s*kg', text)
                if w: data['weight'] = w.group(1)
            elif "Measurements:" in text:
                m = re.findall(r'\d+', text)
                if len(m) >= 3: data['measurements'] = f"{m[0]}-{m[1]}-{m[2]}"
            elif "Ethnicity:" in text:
                data['ethnicity'] = text.replace("Ethnicity:", "").strip()
            elif "Hair color:" in text:
                data['hair_color'] = text.replace("Hair color:", "").strip()
            elif "Eye color:" in text:
                data['eye_color'] = text.replace("Eye color:", "").strip()
            elif "Years active:" in text:
                y = re.search(r'(\d{4})', text)
                if y: data['years_active'] = y.group(1)
            elif "Body type:" in text:
                data['body_type'] = text.replace("Body type:", "").strip()

        # Fallback para país se Birthplace falhar mas tiver Nationality
        if not data.get('birthplace'):
            for li in all_li:
                if "Nationality:" in li.get_text():
                    data['birthplace'] = li.get_text().replace("Nationality:", "").replace("(","").replace(")","").strip()

        data['source_url'] = url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
