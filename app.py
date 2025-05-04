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
    app.logger.info("Starting HTML parsing using 'biolist' structure...")

    try:
        # 1. Encontra a lista UL com id 'biolist'
        biolist = soup.find('ul', id='biolist')

        if not biolist:
            app.logger.warning("Could not find <ul id='biolist'>. Data extraction might fail.")
            return data # Retorna vazio se a lista principal não for encontrada

        # Mapeamento do texto da label para a nossa chave de dados interna
        label_map = {
            "Age:": "age_raw", # Guarda a string completa da idade
            "Born:": "born",
            "Birthplace:": "birthplace",
            "Ethnicity:": "ethnicity",
            "Sexuality:": "sexuality", # Campo novo
            "Profession:": "profession", # Campo novo
            "Hair color:": "hair_color",
            "Eye color:": "eye_color",
            "Height:": "height",
            "Weight:": "weight",
            "Body type:": "body_type",
            "Measurements:": "measurements",
            "Bra/cup size:": "bra_cup_size", # Campo novo
            "Boobs:": "boobs_type", # Campo novo (Fake/Enhanced)
            "Pubic hair:": "pubic_hair", # Campo novo
            "Years active:": "years_active",
            "Tattoos:": "tattoos", # Campo novo
            "Piercings:": "piercings", # Campo novo
            "Instagram follower count:": "instagram_followers" # Campo novo
            # Adicione outras labels se necessário
        }

        # 2. Itera sobre cada item <li> dentro da lista
        for li_item in biolist.find_all('li', recursive=False): # recursive=False para pegar só filhos diretos
            # 3. Encontra o span da label dentro do <li>
            label_span = li_item.find('span', class_='label')
            if not label_span:
                continue # Pula este <li> se não encontrar a label

            label_text = label_span.get_text(strip=True) # Ex: "Born:"

            # 4. Verifica se a label é uma das que queremos
            if label_text in label_map:
                data_key = label_map[label_text] # Ex: "born"

                # 5. Pega o nó irmão *seguinte* à label (deve ser o texto do valor)
                value_node = label_span.next_sibling
                raw_value = None
                if value_node and isinstance(value_node, str):
                    raw_value = value_node.strip()
                elif value_node and value_node.name == 'a':
                     # Caso especial onde o valor é um link (ex: Birthplace, Hair color)
                     # Pega o texto do link e talvez o texto seguinte se houver (país)
                     raw_value = value_node.get_text(strip=True)
                     # Tenta pegar o texto após o link (ex: ", United States")
                     after_link_node = value_node.next_sibling
                     if after_link_node and isinstance(after_link_node, str) and after_link_node.strip().startswith(','):
                         raw_value += after_link_node.strip()

                if raw_value:
                    app.logger.info(f"Found label '{label_text}' -> Raw value: '{raw_value}'")

                    # 6. Aplica limpeza/formatação específica
                    if data_key == 'born':
                        # Tenta formatar a data completa que vem após a label
                        data[data_key] = format_babepedia_date(raw_value)
                    elif data_key == 'birthplace':
                        # A função auxiliar já pega a última parte
                        data[data_key] = extract_country(raw_value)
                    elif data_key == 'height':
                        data[data_key] = extract_cm(raw_value)
                    elif data_key == 'weight':
                        data[data_key] = extract_kg(raw_value)
                    elif data_key == 'years_active':
                        data[data_key] = extract_start_year(raw_value)
                    elif data_key == 'measurements':
                        # O valor já vem mais limpo aqui
                        cleaned_value = raw_value.split('Bra/cup size:')[0].strip()
                        data[data_key] = cleaned_value
                        # Tenta extrair BWH das medidas
                        parts = cleaned_value.split('-')
                        if len(parts) == 3:
                            data['Boobs'] = extract_first_number(parts[0])
                            data['Waist'] = extract_first_number(parts[1])
                            data['Ass'] = extract_first_number(parts[2])
                    elif data_key == 'profession' or data_key == 'tattoos' or data_key == 'piercings':
                         # Para campos que podem ter múltiplos valores com links ou texto
                         # Pega todo o texto dentro do <li> após a label
                         all_texts = [text for text in li_item.stripped_strings if text != label_text]
                         data[data_key] = " ".join(all_texts).strip()
                    elif data_key == 'hair_color' or data_key == 'eye_color' or data_key == 'body_type' or data_key == 'boobs_type':
                         # Pega o texto do primeiro link ou o texto direto
                         link = li_item.find('a')
                         if link:
                             data[data_key] = link.get_text(strip=True)
                         elif raw_value: # Fallback para texto direto se não houver link
                              data[data_key] = raw_value
                    else:
                        # Para outros campos, usa o valor bruto extraído (já stripado)
                        data[data_key] = raw_value
                else:
                    app.logger.warning(f"Found label '{label_text}' but could not extract a valid text value after it.")

    except Exception as e:
        app.logger.error(f"Error during HTML parsing within 'biolist': {e}", exc_info=True)

    # Remove chaves cujo valor final é None ou vazio
    data_cleaned = {k: v for k, v in data.items() if v is not None and v != ''}

    app.logger.info(f"Finished parsing. Extracted data (cleaned): {data_cleaned}")
    return data_cleaned
    

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
