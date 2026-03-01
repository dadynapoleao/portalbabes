async function fetchActressDataFromAPI() {
    if (!actressNameInput || !createActressForm || !actressNameErrorMessage) return;
    const actressName = actressNameInput.value.trim();
    if (!actressName) return;

    actressNameErrorMessage.textContent = 'Buscando dados na API...';
    actressNameErrorMessage.className = 'error-message api-feedback';
    actressNameErrorMessage.style.display = 'block';

    try {
        const response = await fetch('https://portalbabes.onrender.com/scrape_babe?name=' + encodeURIComponent(actressName));
        const data = await response.json();
        
        if (!response.ok) throw new Error(data.error || 'Erro na API');

        // Mapeamento direto entre Chave da API e ID do Input
        const map = {
            'born': 'born',
            'birthplace': 'birthplace',
            'ethnicity': 'ethnicity',
            'hair_color': 'hair_color',
            'eye_color': 'eye_color',
            'height': 'height',
            'weight': 'weight',
            'measurements': 'measurements',
            'years_active': 'years_active'
        };

        for (const [apiKey, inputId] of Object.entries(map)) {
            const input = createActressForm.querySelector('#' + inputId);
            if (input && data[apiKey]) {
                input.value = data[apiKey];
            }
        }

        actressNameErrorMessage.textContent = 'Dados carregados!';
        setTimeout(() => { actressNameErrorMessage.style.display = 'none'; }, 2000);

    } catch (error) {
        actressNameErrorMessage.textContent = 'API: ' + error.message;
        actressNameErrorMessage.classList.add('error');
    }
}
