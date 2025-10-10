from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from backend.models.models import LinkColeta
from backend.modules.utils.config import get_config
from backend.modules.utils.selenium_client import SeleniumClient


class LinkParser:
    """
    Responsável por processar links da tabela links_coleta:
    - Lê links ativos da tabela
    - Paraleliza o parsing em múltiplos workers
    - Marca links como inativos após parsing bem-sucedido
    - Mantém links ativos em caso de falha para retry
    - Limpa links expirados (TTL de 1 dia)
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.max_workers = max(1, int(get_config("LINK_PARSER_WORKERS", "3")))
        self.ttl_days = int(get_config("LINK_PARSER_TTL_DAYS", "1"))

    def cleanup_expired_links(self):
        """Remove links com TTL expirado (mais de N dias ativos sem sucesso)."""
        cutoff = datetime.utcnow() - timedelta(days=self.ttl_days)
        try:
            deleted = self.db.query(LinkColeta).filter(
                LinkColeta.ativo == True,
                LinkColeta.criado_em < cutoff
            ).delete()
            self.db.commit()
            print(f"[LinkParser] Removidos {deleted} links expirados (TTL={self.ttl_days} dias)")
        except Exception as e:
            self.db.rollback()
            print(f"[LinkParser] Erro ao limpar links expirados: {e}")

    def get_pending_links(self, limit: Optional[int] = None) -> List[LinkColeta]:
        """Retorna links ativos que ainda precisam ser processados."""
        query = self.db.query(LinkColeta).filter(LinkColeta.ativo == True)
        if limit:
            query = query.limit(limit)
        return query.all()

    def mark_link_processed(self, link_id: int, success: bool = True):
        """Marca um link como processado (inativo) ou incrementa tentativas em caso de falha."""
        try:
            link = self.db.query(LinkColeta).filter(LinkColeta.id == link_id).first()
            if not link:
                return
            
            if success:
                link.ativo = False
                link.processado_em = datetime.utcnow()
            else:
                link.tentativas = (link.tentativas or 0) + 1
            
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            print(f"[LinkParser] Erro ao marcar link {link_id}: {e}")

    def _split_chunks(self, data: List, parts: int) -> List[List]:
        """Divide uma lista em N partes aproximadamente iguais."""
        if parts <= 1 or len(data) <= 1:
            return [data]
        size = max(1, math.ceil(len(data) / parts))
        return [data[i:i+size] for i in range(0, len(data), size)]

    def parse_links_parallel(
        self,
        links: List[LinkColeta],
        parser_factory
    ) -> List[Dict]:
        """
        Processa links em paralelo usando múltiplos workers.
        
        Args:
            links: Lista de LinkColeta para processar
            parser_factory: Função que recebe (link, client) e retorna dict parseado
        
        Returns:
            Lista de dicts com dados parseados
        """
        if not links:
            return []

        if self.max_workers <= 1 or len(links) <= 1:
            # Processamento sequencial
            results = []
            client = SeleniumClient(user_data_dir="", profile_dir="", detach=False, log_error=None)
            try:
                for link in links:
                    try:
                        data = parser_factory(link, client)
                        if data:
                            results.append(data)
                            self.mark_link_processed(link.id, success=True)
                        else:
                            self.mark_link_processed(link.id, success=False)
                    except Exception as e:
                        print(f"[LinkParser] Erro ao parsear {link.url}: {e}")
                        self.mark_link_processed(link.id, success=False)
            finally:
                try:
                    client.close()
                except Exception:
                    pass
            return results

        # Processamento paralelo
        workers = min(self.max_workers, len(links))
        chunks = self._split_chunks(links, workers)
        results: List[Dict] = []
        clients: List[SeleniumClient] = []

        try:
            # Criar clientes para cada worker
            for _ in range(len(chunks)):
                cli = SeleniumClient(user_data_dir="", profile_dir="", detach=False, log_error=None)
                clients.append(cli)

            with ThreadPoolExecutor(max_workers=len(chunks)) as ex:
                futures = []
                
                for idx, chunk in enumerate(chunks):
                    client = clients[idx]
                    
                    def run_chunk(items: List[LinkColeta], cli: SeleniumClient, worker_id: int):
                        out = []
                        for link in items:
                            try:
                                data = parser_factory(link, cli)
                                if data:
                                    out.append(data)
                                    self.mark_link_processed(link.id, success=True)
                                else:
                                    self.mark_link_processed(link.id, success=False)
                            except Exception as e:
                                print(f"[LinkParser Worker {worker_id}] Erro ao parsear {link.url}: {e}")
                                self.mark_link_processed(link.id, success=False)
                        return out
                    
                    print(f"[LinkParser] Iniciando worker {idx+1}/{len(chunks)} com {len(chunk)} links...")
                    futures.append(ex.submit(run_chunk, chunk, client, idx+1))
                
                for fut in as_completed(futures):
                    try:
                        results.extend(fut.result())
                    except Exception as e:
                        print(f"[LinkParser] Erro no worker: {e}")
        
        finally:
            for cli in clients:
                try:
                    cli.close()
                except Exception:
                    pass
        
        return results
