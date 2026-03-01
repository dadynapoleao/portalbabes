import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
from bs4 import BeautifulSoup
import logging
import re

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def extract_numbers(text):
    return re.findall(r'\d+', str(text))

@app.route('/scrape_babe')
def scrape_babe():
    name = request.args.get('name')
    if not name: return jsonify({"error": "Nome obrigatorio"}), 400
    
    url = f'https://www.babepedia.com/babe/{name.replace(" ", "_")}'
    
    try:
        response = scraper.get(url, timeout=15)
        if response.status_code == 404:
            return jsonify({"error": "Atriz nao encontrada"}), 404
        
        soup = BeautifulSoup(response.content, 'html.parser')
        data = {}
        
        # Encontra a lista de biografia
        biolist = soup.find('ul', id='biolist')
        if biolist:
            for li in biolist.find_all('li'):
                label_tag = li.find('span', class_='label') or li.find('strong')
                if not label_tag: continue
                
                label = label_tag.get_text().strip().lower()
                # Pega o texto logo após o label, removendo o próprio label do texto do LI
                value = li.get_text().replace(label_tag.get_text(), "").strip()

                if "born:" in label:
                    # Tenta formatar a data simplificada
                    data['born'] = value.split(' (')[0] 
                elif "birthplace:" in label:
                    data['birthplace'] = value.split(',')[-1].strip()
                elif "ethnicity:" in label:
                    data['ethnicity'] = value
                elif "measurements:" in label:
                    nums = extract_numbers(value)
                    if len(nums) >= 3:
                        data['measurements'] = f"{nums[0]}-{nums[1]}-{nums[2]}"
                elif "height:" in label:
                    nums = extract_numbers(value)
                    if nums: data['height'] = nums[0]
                elif "weight:" in label:
                    nums = extract_numbers(value)
                    if nums: data['weight'] = nums[0]
                elif "hair color:" in label:
                    data['hair_color'] = value
                elif "eye color:" in label:
                    data['eye_color'] = value
                elif "body type:" in label:
                    data['body_type'] = value
                elif "years active:" in label:
                    nums = extract_numbers(value)
                    if nums: data['years_active'] = nums[0]

        data['source_url'] = url
        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))
