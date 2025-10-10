from __future__ import annotations

from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.models.models import LinkColeta


class LinkCollectorService:
    """
    Responsável por gerenciar a gravação de links coletados na tabela links_coleta.
    - Evita duplicatas (mesmo URL + source)
    - Não reinsere links já ativos
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.stats = {
            "total_received": 0,
            "inserted": 0,
            "duplicates": 0,
            "errors": 0
        }

    def save_links(self, links: List[Dict]) -> Dict:
        """
        Grava uma lista de links no banco de dados.
        
        Args:
            links: Lista de dicts com keys 'url' e 'source'
        
        Returns:
            Dict com estatísticas da operação
        """
        self.stats["total_received"] = len(links)
        
        for link_data in links:
            url = link_data.get("url_base") or link_data.get("url")
            source = link_data.get("source")
            
            if not url or not source:
                self.stats["errors"] += 1
                continue
            
            # Verifica se o link já existe e está ativo
            existing = self.db.query(LinkColeta).filter(
                LinkColeta.url == url,
                LinkColeta.source == source,
                LinkColeta.ativo == True
            ).first()
            
            if existing:
                self.stats["duplicates"] += 1
                continue
            
            # Tenta inserir novo link
            try:
                new_link = LinkColeta(
                    url=url,
                    source=source,
                    ativo=True,
                    tentativas=0
                )
                self.db.add(new_link)
                self.db.commit()
                self.stats["inserted"] += 1
            except IntegrityError:
                # Violação da constraint unique (url, source)
                self.db.rollback()
                self.stats["duplicates"] += 1
            except Exception as e:
                self.db.rollback()
                print(f"[LinkCollectorService] Erro ao inserir link {url}: {e}")
                self.stats["errors"] += 1
        
        return self.stats
