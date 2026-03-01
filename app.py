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

def format_date_flexible(text):
    # Converte qualquer formato de data do site para YYYY/MM/DD
    months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
    text = text.lower()
    # Busca por um ano de 4 dígitos
    year_match = re.search(r'\d{4}', text)
    if not year_match: return text
    year = year_match.group(0)
    
    # Busca o nome do mês
    month = "01"
    for m_name, m_num in months.items():
        if m_name in text:
            month = m_num
            break
            
    # Busca o dia (número de 1 ou 2 dígitos que não seja o ano)
    days = re.findall(r'\b\d{1,2}\b', text)
    day = "01"
    if days: day = days[0].zfill(2)
    
    return f"{year}/{month}/{day}"

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Falta nome"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = {}
        
        # Estratégia: Varre todos os itens de lista (li) da página
        for li in soup.find_all('li'):
            text = li.get_text(separator=" ").strip()
            text_lower = text.lower()
            
            # Nascimento
            if "born:" in text_lower:
                val = text.split(":", 1)[1].strip()
                data['born'] = format_date_flexible(val)
            
            # Medidas (Busca padrão 00-00-00)
            elif "measurements:" in text_lower:
                m = re.findall(r'\d+', text)
                if len(m) >= 3: data['measurements'] = f"{m[0]}-{m[1]}-{m[2]}"
            
            # Altura (Busca número antes de "cm")
            elif "height:" in text_lower:
                h = re.search(r'(\d+)\s*cm', text)
                if h: data['height'] = h.group(1)
            
            # Peso (Busca número antes de "kg")
            elif "weight:" in text_lower:
                w = re.search(r'(\d+)\s*kg', text)
                if w: data['weight'] = w.group(1)
            
            # Etnia / País / Cabelo
            elif "ethnicity:" in text_lower:
                data['ethnicity'] = text.split(":", 1)[1].strip()
            elif "birthplace:" in text_lower:
                data['birthplace'] = text.split(",")[-1].strip()
            elif "hair color:" in text_lower:
                data['hair_color'] = text.split(":", 1)[1].strip()
            elif "eye color:" in text_lower:
                data['eye_color'] = text.split(":", 1)[1].strip()

        data['source_url'] = url
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
