from typing import Optional, Dict
import time
from backend.modules.utils.selenium_client import SeleniumClient
from backend.modules.utils.config import get_config

# Lista de sites de coleta para exportar cookies
COLLECTION_SITES = [
    "https://www.mercadolivre.com.br",
    "https://www.amazon.com.br"
]

def update_all_site_cookies(user_data_dir: Optional[str] = None, profile_dir: Optional[str] = None) -> Dict[str, dict]:
    """
    Função genérica para atualizar cookies de todos os sites de coleta.
    Abre uma sessão do Chrome com o perfil logado, navega em cada site e exporta os cookies.
    Retorna dict {url: {cookies: [...], localStorage: {...}}}
    """
    user_data = (get_config("SELENIUM_USER_DATA_DIR", user_data_dir or "") or "").strip()
    profile = (get_config("SELENIUM_PROFILE_DIR", profile_dir or "") or "").strip()
    
    print(f"Abrindo sessão do Chrome com perfil logado para exportar cookies...")
    selenium_client = SeleniumClient(
        user_data_dir=user_data,
        profile_dir=profile,
        detach=False,
        log_error=None,
    )
    
    all_cookies = {}
    try:
        for site_url in COLLECTION_SITES:
            print(f"  Exportando cookies de: {site_url}")
            try:
                # Pequeno delay antes de chamar o Selenium para reduzir problemas de timing
                time.sleep(2)
                session_state = selenium_client.export_session_state(site_url)
                all_cookies[site_url] = session_state
                print(f"    ✓ {len(session_state.get('cookies', []))} cookies exportados")
            except Exception as e:
                print(f"    ✗ Erro ao exportar cookies de {site_url}: {e}")
                all_cookies[site_url] = {"cookies": [], "localStorage": {}}
    finally:
        try:
            selenium_client.close()
        except Exception:
            pass
    
    return all_cookies