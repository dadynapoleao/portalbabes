# --- Imports ---
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper  # SUBSTITUÍDO: de requests para cloudscraper
from bs4 import BeautifulSoup
import logging
import re

# ... (Mantenha as funções auxiliares de extração iguais) ...

# Crie o scraper globalmente para maior eficiência
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

# --- Função Principal de Scraping Atualizada ---
def scrape_babepedia_data(babe_name_formatted):
    babe_name_for_url = babe_name_formatted
    url = f'https://www.babepedia.com/babe/{babe_name_for_url}'
    
    scraped_info = {}
    try:
        app.logger.info(f"Requesting URL via CloudScraper: {url}")
        
        # USANDO SCRAPER NO LUGAR DE REQUESTS
        response = scraper.get(url, timeout=15)
        
        # Se ainda der 403, tentamos forçar um novo scraper
        if response.status_code == 403:
             app.logger.warning("403 detectado, tentando novo bypass...")
             temp_scraper = cloudscraper.create_scraper()
             response = temp_scraper.get(url, timeout=15)

        response.raise_for_status()
        
        app.logger.info(f"Request successful (Status: {response.status_code}). Parsing content...")
        soup = BeautifulSoup(response.content, 'html.parser')
        scraped_info = parse_html_data(soup)
        
        # ... (resto da lógica de sucesso) ...
        scraped_info['searched_name'] = babe_name_formatted
        scraped_info['source_url'] = url

    except Exception as e:
        status_code = getattr(e.response, 'status_code', 500) if hasattr(e, 'response') else 500
        app.logger.error(f"Error scraping {url}: {e}")
        scraped_info = {"error": f"Erro no Scraping: {str(e)}", "status_code": status_code}
        
    return scraped_info
