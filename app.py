import os
from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import logging

# Configura o Flask App
app = Flask(__name__)

# Configura logging básico para ver mensagens nos logs do Render
logging.basicConfig(level=logging.INFO)
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers.extend(gunicorn_logger.handlers)
app.logger.setLevel(logging.INFO)

# --- Função para extrair dados específicos da Babepedia ---
# !! ESTA É A PARTE MAIS IMPORTANTE E FRÁGIL !!
# !! VOCÊ PRECISA INSPECIONAR O HTML DA BABEPEDIA E ADAPTAR OS SELETORES BS4 !!
def parse_html_data(soup):
    data = {}
    app.logger.info("Starting HTML parsing...")

    try:
        # Exemplo: Encontrar a div com ID 'bio' (INSPECIONE O SITE REAL PARA CONFIRMAR SE O ID É ESSE!)
        bio_div = soup.find('div', id='bio')

        if not bio_div:
            app.logger.warning("Could not find div with id='bio'. Parsing might fail.")
            # Tenta encontrar dados em outros lugares como fallback se a div principal não for encontrada
            # Ou retorna dados vazios/erro

        # ----- EXEMPLOS DE EXTRAÇÃO (PRECISAM SER ADAPTADOS) -----

        # Tenta encontrar o texto "Born:" e pegar o conteúdo seguinte
        born_tag = soup.find(lambda tag: tag.name == "strong" and "Born:" in tag.get_text())
        if born_tag:
            raw_born = born_tag.next_sibling
            if raw_born and isinstance(raw_born, str):
                 data['born_raw'] = raw_born.strip()
                 app.logger.info(f"Found raw born: {data['born_raw']}")
                 # Tenta formatar a data (função precisa ser definida ou importada)
                 # data['born'] = format_babepedia_date(data['born_raw']) # Você precisaria criar esta função
            else:
                app.logger.warning("Found 'Born:' tag but next sibling is not text.")

        # Tenta encontrar "Height:"
        height_tag = soup.find(lambda tag: tag.name == "strong" and "Height:" in tag.get_text())
        if height_tag:
            raw_height = height_tag.next_sibling
            if raw_height and isinstance(raw_height, str):
                data['height_raw'] = raw_height.strip()
                app.logger.info(f"Found raw height: {data['height_raw']}")
                # Tenta extrair cm (função precisa ser definida ou importada)
                # data['height'] = extract_cm(data['height_raw']) # Você precisaria criar esta função
            else:
                 app.logger.warning("Found 'Height:' tag but next sibling is not text.")

        # Tenta encontrar "Weight:" (similar a Height)
        weight_tag = soup.find(lambda tag: tag.name == "strong" and "Weight:" in tag.get_text())
        if weight_tag:
            raw_weight = weight_tag.next_sibling
            if raw_weight and isinstance(raw_weight, str):
                data['weight_raw'] = raw_weight.strip()
                app.logger.info(f"Found raw weight: {data['weight_raw']}")
                # data['weight'] = extract_kg(data['weight_raw']) # Crie esta função

        # Tenta encontrar "Measurements:" (similar)
        measurements_tag = soup.find(lambda tag: tag.name == "strong" and "Measurements:" in tag.get_text())
        if measurements_tag:
            raw_measurements = measurements_tag.next_sibling
            if raw_measurements and isinstance(raw_measurements, str):
                data['measurements_raw'] = raw_measurements.strip().split('Bra/cup size:')[0].strip() # Limpa info extra
                app.logger.info(f"Found raw measurements: {data['measurements_raw']}")
                # data['measurements'] = data['measurements_raw'] # Pode precisar de mais limpeza
                # Tenta extrair B/W/H
                # parts = data['measurements_raw'].split('-')
                # if len(parts) == 3:
                #     data['Boobs'] = parts[0].replace(...)... # Crie lógica de extração BWH

        # ... ADICIONE A LÓGICA BS4 PARA *TODOS* OS OUTROS CAMPOS ...
        # (Birthplace, Ethnicity, Hair color, Eye color, Body type, Years active)
        # Use app.logger.info/warning para depurar

        # ----- FIM DOS EXEMPLOS -----

        if not data:
            app.logger.warning("Parsing finished but no data was extracted. Check selectors.")

    except Exception as e:
        app.logger.error(f"Error during HTML parsing: {e}", exc_info=True)
        # Não levanta erro aqui, apenas retorna o que conseguiu (pode ser vazio)

    app.logger.info(f"Finished parsing. Extracted keys: {list(data.keys())}")
    return data

# --- Função principal de scraping ---
def scrape_babepedia_data(babe_name_formatted):
    url = f'https://www.babepedia.com/babe/{babe_name_formatted}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    scraped_info = {}

    try:
        app.logger.info(f"Requesting URL: {url}")
        # Timeout de 10 segundos para evitar que a requisição trave
        response = requests.get(url, headers=headers, timeout=10)
        # Levanta um erro para status HTTP ruins (4xx ou 5xx)
        response.raise_for_status()

        app.logger.info(f"Request successful (Status: {response.status_code}). Parsing content...")
        soup = BeautifulSoup(response.content, 'html.parser')

        # Chama a função de parsing do HTML
        scraped_info = parse_html_data(soup)

        # Adiciona o nome buscado e a URL para referência, se necessário
        scraped_info['searched_name'] = babe_name_formatted
        scraped_info['source_url'] = url

        # Verificação final: se nenhum dado útil foi extraído
        if not any(key not in ['searched_name', 'source_url'] for key in scraped_info):
             app.logger.warning(f"Scraping completed for {babe_name_formatted}, but no specific data fields were extracted.")
             # Pode-se retornar um indicador de que nada foi achado
             # scraped_info["status"] = "parsed_but_empty"

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        app.logger.error(f"HTTP Error {status_code} for {url}: {e}")
        scraped_info = {"error": f"Atriz não encontrada ou erro na página (Status: {status_code})", "status_code": status_code}
    except requests.exceptions.Timeout:
        app.logger.error(f"Request timed out for {url}")
        scraped_info = {"error": "Timeout ao acessar Babepedia", "status_code": 408}
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request failed for {url}: {e}")
        scraped_info = {"error": f"Falha na conexão com Babepedia: {e}", "status_code": 503} # Service Unavailable
    except Exception as e:
        app.logger.error(f"Unexpected error during scraping for {babe_name_formatted}: {e}", exc_info=True)
        scraped_info = {"error": f"Erro inesperado no servidor durante o scraping: {e}", "status_code": 500}

    return scraped_info

# --- Define o Endpoint/Rota da API ---
@app.route('/scrape_babe')
def scrape_babe_api():
    # Pega o parâmetro 'name' da URL (?name=...)
    babe_name = request.args.get('name')
    app.logger.info(f"Received request for name: {babe_name}")

    if not babe_name:
        app.logger.warning("Request received without 'name' parameter.")
        return jsonify({"error": "Parâmetro 'name' é obrigatório"}), 400

    # Chama a função de scraping
    scraped_data = scrape_babepedia_data(babe_name)

    # Verifica se houve erro durante o scraping e retorna o erro/status adequado
    if "error" in scraped_data:
        status = scraped_data.get("status_code", 500)
        app.logger.info(f"Returning error for {babe_name}: Status {status}, Message: {scraped_data['error']}")
        return jsonify(scraped_data), status
    else:
        app.logger.info(f"Successfully scraped data for {babe_name}. Returning JSON.")
        return jsonify(scraped_data) # Retorna os dados como JSON

# O Gunicorn vai rodar a aplicação, então não precisamos de app.run() aqui para o deploy
# if __name__ == '__main__':
#    app.run(debug=True) # Mantenha comentado ou remova para o deploy
