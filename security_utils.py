from playwright.sync_api import Page
import json

def extract_forms(page: Page):
    """Extracts details about all forms on the current page."""
    return page.evaluate("""() => {
        const forms = document.querySelectorAll('form');
        return Array.from(forms).map((form, index) => {
            const inputs = Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
                name: input.name || input.id || '',
                type: input.type || input.tagName.toLowerCase(),
                id: input.id || ''
            }));
            
            return {
                index: index,
                action: form.action || '',
                method: form.method || 'GET',
                inputs: inputs,
                id: form.id || ''
            };
        });
    }""")

def extract_url_params(url: str):
    """Extracts query parameters from a URL."""
    if "?" not in url:
        return []
    
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return list(parse_qs(parsed.query).keys())
