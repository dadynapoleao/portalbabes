# --- Imports ---
import os
from flask import Flask, request, jsonify
from flask_cors import CORS # Importa o CORS
import requests
from bs4 import BeautifulSoup
import logging
import re # Importa regex para ajudar na limpeza (exemplo)

# --- Configuração do Flask App e CORS ---
app = Flask(__name__)
# Inicializa o CORS para permitir requisições de outras origens (necessário para seu JS)
# Por padrão, permite todas as origens (*), o que é bom para desenvolvimento.
# Para produção, considere restringir: CORS(app, origins=["https://seu-dominio-frontend.com"])
CORS(app)

# --- Configuração de Logging ---
# Para que você possa ver mensagens úteis nos logs do Render
logging.basicConfig(level=logging.INFO)
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers.extend(gunicorn_logger.handlers)
app.logger.setLevel(logging.INFO)

# --- Funções Auxiliares de Extração/Formatação (EXEMPLOS - Adapte!) ---

def extract_first_number(text):
    """Extrai a primeira sequência de dígitos de uma string."""
    if not text:
        return None
    match = re.search(r'\d+', str(text))
    return match.group(0) if match else None

def extract_cm(height_text):
    """Tenta extrair o valor em cm da string de altura."""
    if not height_text:
        return None
    # Procura por "(XXX cm)" ou "XXX cm"
    match_paren = re.search(r'\((\d+)\s*cm\)', height_text)
    if match_paren:
        return match_paren.group(1)
    match_direct = re.search(r'(\d+)\s*cm', height_text)
    if match_direct:
        return match_direct.group(1)
    # Fallback: se for só um número tipo '157'
    match_num_only = re.fullmatch(r'(\d{3})', height_text)
    if match_num_only and 100 < int(match_num_only.group(1)) < 250:
        return match_num_only.group(1)
    return None # Não conseguiu extrair

def extract_kg(weight_text):
    """Tenta extrair o valor em kg da string de peso."""
    if not weight_text:
        return None
    # Procura por "(XX kg)" ou "XX kg"
    match_paren = re.search(r'\((\d+)\s*kg\)', weight_text)
    if match_paren:
        return match_paren.group(1)
    match_direct = re.search(r'(\d+)\s*kg', weight_text)
    if match_direct:
        return match_direct.group(1)
     # Fallback: se for só um número tipo '54'
    match_num_only = re.fullmatch(r'(\d{2,3})', weight_text)
    if match_num_only and 30 < int(match_num_only.group(1)) < 200:
        return match_num_only.group(1)
    return None

def format_babepedia_date(date_text):
    """Tenta formatar datas como 'Friday 20th of December 1985' para YYYY/MM/DD."""
    if not date_text:
        return None
    month_map = {'january': '01', 'february': '02', 'march': '03', 'april': '04', 'may': '05', 'june': '06', 'july': '07', 'august': '08', 'september': '09', 'october': '10', 'november': '11', 'december': '12'}
    # Regex para capturar Dia (com ou sem sufixo), Mês (texto) e Ano (4 dígitos)
    match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-zA-Z]+)\s+(\d{4})', date_text)
    if match:
        day = match.group(1).zfill(2) # Garante 2 dígitos para o dia
        month_name = match.group(2).lower()
        year = match.group(3)
        month_number = month_map.get(month_name)
        if month_number:
            return f"{year}/{month_number}/{day}"
    # Adicione outros regex aqui se houver outros formatos comuns
    app.logger.warning(f"Could not parse date format: {date_text}")
    return date_text # Retorna original se não conseguiu parsear

def extract_country(birthplace_text):
    """Extrai o país, geralmente a última parte após vírgula."""
    if not birthplace_text:
        return None
    parts = birthplace_text.split(',')
    return parts[-1].strip() if parts else None

def extract_start_year(active_text):
    """Extrai o ano inicial de 'YYYY - present'."""
    if not active_text:
        return None
    match = re.search(r'^(\d{4})\s*-\s*present', active_text)
    return match.group(1) if match else None

# --- Função para Parsear o HTML (ADAPTE OS SELETORES!) ---
def parse_html_data(soup):
    data = {}
    app.logger.info("Starting HTML parsing...")

    try:
        # Tenta encontrar a div principal que parece conter as stats (pode mudar!)
        # Inspecione a página e ajuste 'div', '#bio' conforme necessário
        stats_container = soup.find('div', id='bio') # Ou outra div/section relevante

        if not stats_container:
            app.logger.warning("Could not find primary stats container (e.g., div#bio). Searching page globally.")
            # Usa 'soup' (página inteira) como fallback se o container não for encontrado
            stats_container = soup

        # Mapeamento de texto âncora (em negrito) para a chave no nosso objeto data
        # A ordem pode importar se a estrutura for consistente
        label_map = {
            "Born:": "born",
            "Birthplace:": "birthplace",
            "Ethnicity:": "ethnicity",
            "Hair color:": "hair_color",
            "Eye color:": "eye_color",
            "Height:": "height",
            "Weight:": "weight",
            "Body type:": "body_type",
            "Measurements:": "measurements",
            "Years active:": "years_active",
            # Adicione outras labels que você quer extrair
        }

        # Encontra todas as tags <strong> (ou a tag que contém a label)
        # dentro do container (ou da página inteira se container falhou)
        strong_tags = stats_container.find_all('strong')
        app.logger.info(f"Found {len(strong_tags)} <strong> tags.")

        for tag in strong_tags:
            label_text = tag.get_text(strip=True) # Pega o texto da label (ex: "Born:")
            if label_text in label_map:
                data_key = label_map[label_text] # Mapeia para nossa chave (ex: "born")
                # Pega o texto que vem *depois* da tag <strong>
                raw_value = tag.next_sibling
                if raw_value and isinstance(raw_value, str) and raw_value.strip():
                    value = raw_value.strip()
                    app.logger.info(f"Found label '{label_text}' -> Raw value: '{value}'")

                    # Aplica formatação/extração específica baseada na chave
                    if data_key == 'born':
                        data['born'] = format_babepedia_date(value)
                    elif data_key == 'birthplace':
                        data['birthplace'] = extract_country(value)
                    elif data_key == 'height':
                        data['height'] = extract_cm(value)
                    elif data_key == 'weight':
                        data['weight'] = extract_kg(value)
                    elif data_key == 'years_active':
                        data['years_active'] = extract_start_year(value)
                    elif data_key == 'measurements':
                        cleaned_value = value.split('Bra/cup size:')[0].strip() # Remove info extra
                        data['measurements'] = cleaned_value
                        # Tenta extrair BWH de 'measurements'
                        parts = cleaned_value.split('-')
                        if len(parts) == 3:
                            data['Boobs'] = extract_first_number(parts[0])
                            data['Waist'] = extract_first_number(parts[1])
                            data['Ass'] = extract_first_number(parts[2])
                    else:
                        # Para outros campos, apenas guarda o valor limpo
                        data[data_key] = value.strip()

                else:
                    app.logger.warning(f"Found label '{label_text}' but next sibling was not valid text.")

        if not data:
            app.logger.warning("Parsing finished but no data was extracted via labels. Check selectors/structure.")

    except Exception as e:
        app.logger.error(f"Error during HTML parsing: {e}", exc_info=True)

    app.logger.info(f"Finished parsing. Extracted data: {data}")
    return data

# --- Função Principal de Scraping ---
def scrape_babepedia_data(babe_name_formatted):
    url = f'https://www.babepedia.com/babe/{babe_name_formatted}'
    headers = {
        # Cabeçalho User-Agent para simular um navegador
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    scraped_info = {}

    try:
        app.logger.info(f"Requesting URL: {url}")
        # Adiciona um timeout razoável (ex: 10 segundos)
        response = requests.get(url, headers=headers, timeout=10)
        # Levanta um erro HTTP para status ruins (404, 500, etc.)
        response.raise_for_status()

        app.logger.info(f"Request successful (Status: {response.status_code}). Parsing content...")
        soup = BeautifulSoup(response.content, 'html.parser')

        # Chama a função de parsing para extrair os dados do HTML
        scraped_info = parse_html_data(soup)

        # Adiciona informações de referência (opcional)
        scraped_info['searched_name'] = babe_name_formatted
        scraped_info['source_url'] = url

        # Verifica se algum dado útil foi realmente extraído
        useful_keys = [k for k in scraped_info if k not in ['searched_name', 'source_url']]
        if not useful_keys:
             app.logger.warning(f"Scraping for {babe_name_formatted} completed, but no specific data fields were extracted by the parser.")
             # Você pode querer retornar um status específico aqui
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
        scraped_info = {"error": f"Falha na conexão com Babepedia: {e}", "status_code": 503}
    except Exception as e:
        app.logger.error(f"Unexpected error during scraping for {babe_name_formatted}: {e}", exc_info=True)
        scraped_info = {"error": f"Erro inesperado no servidor durante o scraping.", "status_code": 500} # Não expõe detalhes do erro

    return scraped_info

# --- Endpoint da API (/scrape_babe) ---
@app.route('/scrape_babe')
def scrape_babe_api():
    # Pega o parâmetro 'name' da URL (ex: ?name=Savanah_Storm)
    babe_name = request.args.get('name')
    app.logger.info(f"Received request for name: {babe_name}")

    if not babe_name:
        app.logger.warning("Request received without 'name' parameter.")
        # Retorna um erro 400 (Bad Request) se o nome não for fornecido
        return jsonify({"error": "Parâmetro 'name' é obrigatório"}), 400

    # Chama a função que faz o scraping
    scraped_data = scrape_babepedia_data(babe_name)

    # Verifica se o scraping retornou um erro
    if "error" in scraped_data:
        # Retorna o JSON de erro com o status code apropriado
        status = scraped_data.get("status_code", 500)
        app.logger.info(f"Returning error for {babe_name}: Status {status}, Message: {scraped_data['error']}")
        return jsonify(scraped_data), status
    else:
        # Se tudo correu bem, retorna os dados extraídos como JSON com status 200 OK
        app.logger.info(f"Successfully scraped data for {babe_name}. Returning JSON.")
        return jsonify(scraped_data)

# --- Bloco para rodar localmente para teste (NÃO usado pelo Gunicorn no Render) ---
# if __name__ == '__main__':
#     # Roda o servidor Flask em modo de debug localmente na porta 5000 (ou outra)
#     # Use 'python app.py' no terminal para iniciar localmente
#     # Lembre-se de comentar ou remover isso antes de fazer o push para o Render
#     app.run(debug=True, port=5001)
