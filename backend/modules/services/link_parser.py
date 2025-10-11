"""
Serviço para parsing paralelo de links coletados.
Lê links ativos da tabela links_coleta e processa usando múltiplas threads.
"""
import logging
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.modules.collectors.ml_collector import MLCollector
from backend.modules.services.link_service import LinkService
from backend.modules.services.offer_processor import OfferProcessor
from backend.modules.utils.config import get_config
from backend.models.models import LinkColeta
from backend.db.database import SessionLocal


class LinkParser:
    """
    Gerencia o parsing paralelo de links.
    Cada origem (source) tem seu próprio collector e método de parsing.
    """
    
    def __init__(self, db_session):
        self.db = db_session
        self.link_service = LinkService(db_session)
        self.max_workers = max(1, int(get_config("LINK_PARSER_WORKERS", "3")))
    
    def _parse_single_link(self, link: LinkColeta) -> bool:
        """
        Faz o parsing de um único link.
        Cria seu próprio collector e sessão de DB para thread-safety.
        
        Args:
            link: Objeto LinkColeta com url e source
        
        Returns:
            True se o parsing foi bem-sucedido
        """
        collector = None
        db_session = None
        try:
            # Cria uma nova sessão de DB para esta thread
            db_session = SessionLocal()
            link_service = LinkService(db_session)
            offer_processor = OfferProcessor(db_session)
            
            # Cria um collector específico para esta thread
            if link.source == "mercadolivre":
                collector = MLCollector()
            else:
                raise ValueError(f"Source não suportada: {link.source}")
            
            # Faz o parsing do link
            logging.info(f"Parsing link {link.id}: {link.url}")
            parsed_data = collector.parse_link(link.url)
            
            # Processa o item parseado
            offer_created, outcome, product_created = offer_processor.process_item(parsed_data)
            
            # Marca como parseado com sucesso
            link_service.mark_as_parsed(link.id)
            logging.info(f"Link {link.id} parseado com sucesso. Outcome: {outcome}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Erro ao parsear link {link.id}: {error_msg}")
            if db_session:
                link_service = LinkService(db_session)
                link_service.mark_as_failed(link.id, error_msg)
            return False
        finally:
            # Limpa recursos da thread
            if collector:
                try:
                    collector.close()
                except Exception:
                    pass
            if db_session:
                try:
                    db_session.close()
                except Exception:
                    pass
    
    def parse_active_links(self, source: Optional[str] = None, limit: Optional[int] = None) -> Dict:
        """
        Processa links ativos em paralelo.
        
        Args:
            source: Filtrar por origem específica (opcional)
            limit: Limitar número de links a processar (opcional)
        
        Returns:
            Estatísticas do processamento
        """
        # Busca links ativos
        active_links = self.link_service.get_active_links(source=source, limit=limit)
        
        if not active_links:
            logging.info("Nenhum link ativo para processar")
            return {
                "total": 0,
                "success": 0,
                "failed": 0
            }
        
        logging.info(f"Processando {len(active_links)} links ativos...")
        
        stats = {
            "total": len(active_links),
            "success": 0,
            "failed": 0
        }
        
        # Processa em paralelo se tivermos múltiplos workers
        if self.max_workers > 1 and len(active_links) > 1:
            stats = self._parse_parallel(active_links)
        else:
            # Processa sequencialmente
            for link in active_links:
                if self._parse_single_link(link):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
        
        logging.info(f"Parsing concluído. Stats: {stats}")
        return stats
    
    def _parse_parallel(self, links: List[LinkColeta]) -> Dict:
        """
        Processa links em paralelo usando ThreadPoolExecutor.
        
        Args:
            links: Lista de objetos LinkColeta
        
        Returns:
            Estatísticas do processamento
        """
        stats = {
            "total": len(links),
            "success": 0,
            "failed": 0
        }
        
        # Cria um collector para cada worker
        # Isso evita compartilhar o driver selenium entre threads
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submete todas as tarefas
            future_to_link = {
                executor.submit(self._parse_single_link, link): link
                for link in links
            }
            
            # Coleta resultados conforme completam
            for future in as_completed(future_to_link):
                link = future_to_link[future]
                try:
                    success = future.result()
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logging.error(f"Exceção não tratada no parsing do link {link.id}: {e}")
                    stats["failed"] += 1
                    self.link_service.mark_as_failed(link.id, str(e))
        
        return stats
    
    def cleanup(self):
        """Limpa recursos (placeholder - cada thread limpa seus próprios recursos)."""
        pass
