"""
Serviço para gerenciamento de links de coleta.
Responsável por:
- Persistir links coletados
- Recuperar links ativos para parsing
- Marcar links como parseados/inativos
- Limpar links expirados (TTL)
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.exc import IntegrityError

from backend.models.models import LinkColeta


class LinkService:
    """Gerencia o ciclo de vida dos links coletados."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def save_links(self, links: List[Dict], source: str) -> int:
        """
        Salva uma lista de links na tabela links_coleta.
        Ignora duplicatas (mesma URL + source).
        
        Args:
            links: Lista de dicts com pelo menos a chave 'url_base'
            source: Identificador da origem (ex: "mercadolivre")
        
        Returns:
            Número de links novos inseridos
        """
        inserted_count = 0
        
        for link_data in links:
            url = link_data.get("url_base")
            if not url:
                continue
            
            # Verifica se já existe (ativo ou não)
            existing = self.db.query(LinkColeta).filter(
                LinkColeta.url == url,
                LinkColeta.source == source
            ).first()
            
            if existing:
                # Se já existe e está inativo, reativa para nova tentativa
                if not existing.ativo:
                    existing.ativo = True
                    existing.tentativas = 0
                    existing.ultimo_erro = None
                    try:
                        self.db.commit()
                    except Exception:
                        self.db.rollback()
                continue
            
            # Cria novo registro
            try:
                link = LinkColeta(
                    url=url,
                    source=source,
                    ativo=True,
                    tentativas=0
                )
                self.db.add(link)
                self.db.commit()
                inserted_count += 1
            except IntegrityError:
                # Race condition - outro processo já inseriu
                self.db.rollback()
            except Exception as e:
                self.db.rollback()
                print(f"Erro ao salvar link {url}: {e}")
        
        return inserted_count
    
    def get_active_links(self, source: Optional[str] = None, limit: Optional[int] = None) -> List[LinkColeta]:
        """
        Recupera links ativos para parsing.
        
        Args:
            source: Filtrar por origem específica (opcional)
            limit: Limitar número de resultados (opcional)
        
        Returns:
            Lista de objetos LinkColeta ativos
        """
        query = self.db.query(LinkColeta).filter(LinkColeta.ativo == True)
        
        if source:
            query = query.filter(LinkColeta.source == source)
        
        # Ordena pelos mais antigos primeiro
        query = query.order_by(LinkColeta.criado_em.asc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def mark_as_parsed(self, link_id: int) -> bool:
        """
        Marca um link como parseado com sucesso (inativa).
        
        Args:
            link_id: ID do link
        
        Returns:
            True se atualizado com sucesso
        """
        try:
            link = self.db.query(LinkColeta).filter(LinkColeta.id == link_id).first()
            if link:
                link.ativo = False
                link.parseado_em = datetime.utcnow()
                self.db.commit()
                return True
        except Exception as e:
            self.db.rollback()
            print(f"Erro ao marcar link {link_id} como parseado: {e}")
        return False
    
    def mark_as_failed(self, link_id: int, error_msg: str) -> bool:
        """
        Registra falha no parsing de um link.
        Mantém o link ativo para retry.
        
        Args:
            link_id: ID do link
            error_msg: Mensagem de erro
        
        Returns:
            True se atualizado com sucesso
        """
        try:
            link = self.db.query(LinkColeta).filter(LinkColeta.id == link_id).first()
            if link:
                link.tentativas += 1
                link.ultimo_erro = error_msg[:500] if error_msg else None
                self.db.commit()
                return True
        except Exception as e:
            self.db.rollback()
            print(f"Erro ao marcar link {link_id} como falho: {e}")
        return False
    
    def cleanup_expired_links(self, ttl_hours: int = 24) -> int:
        """
        Remove links expirados (criados há mais de TTL horas).
        
        Args:
            ttl_hours: Tempo de vida em horas (padrão: 24)
        
        Returns:
            Número de links removidos
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=ttl_hours)
            expired = self.db.query(LinkColeta).filter(
                LinkColeta.criado_em < cutoff_time
            ).all()
            
            count = len(expired)
            for link in expired:
                self.db.delete(link)
            
            self.db.commit()
            return count
        except Exception as e:
            self.db.rollback()
            print(f"Erro ao limpar links expirados: {e}")
            return 0
