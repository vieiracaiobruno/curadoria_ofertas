from __future__ import annotations

import json
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from sqlalchemy.exc import IntegrityError

from backend.modules.utils.config import get_config
from backend.models.models import (
    Produto, Oferta, LojaConfiavel, HistoricoPreco, Tag, LogColeta
)


class OfferProcessor:
    """
    Responsável por:
      - Persistência de lojas/produtos
      - Auto-tag (opcional)
      - Regras de elegibilidade de oferta
      - Criação da oferta
      - Logging de falhas em LogColeta

    Uso:
      op = OfferProcessor(db_session)
      op.process_item(item_extraido_do_collector)
    """

    def __init__(self, db_session):
        self.db = db_session
        self.require_db_tag_match = (get_config("REQUIRE_DB_TAG_MATCH", "true") or "true").lower() in {"1", "true", "yes", "y"}
        self.auto_tag_on_collect = (get_config("AUTO_TAG_ON_COLLECT", "false") or "false").lower() in {"1", "true", "yes", "y"}
        self._load_db_tags_as_keywords()
        self.stats = {
            "processed_total": 0,
            "erros": 0,
            "novo_produto": 0,
            "produto_existente": 0,
            "novo_produto_oferta_criada": 0,
            "existente_oferta_criada": 0,
            "novo_produto_sem_oferta_store_inativa": 0,
            "existente_sem_oferta_store_inativa": 0,
            "novo_produto_sem_oferta_tag_ineligible": 0,
            "existente_sem_oferta_tag_ineligible": 0,
            "novo_produto_sem_oferta_open_offer": 0,
            "existente_sem_oferta_open_offer": 0,
        }

    # ================= Tags (para regras) =================
    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", s)

    def _compile_pattern_for_tag(self, norm_tag: str):
        if len(norm_tag) <= 3 and re.fullmatch(r"[a-z0-9]+", norm_tag):
            pat = rf"(?<!\w){re.escape(norm_tag)}(?!\w)"
        else:
            pat = re.escape(norm_tag)
        return re.compile(pat, re.IGNORECASE)

    def _load_db_tags_as_keywords(self):
        self._tags_norm = set()
        self._tag_patterns: Dict[str, re.Pattern] = {}
        self._tags_by_norm: Dict[str, Tag] = {}
        tags = self.db.query(Tag).all()
        for t in tags:
            norm = self._normalize_text(t.nome_tag)
            if not norm or norm in self._tags_norm:
                continue
            self._tags_norm.add(norm)
            self._tag_patterns[norm] = self._compile_pattern_for_tag(norm)
            self._tags_by_norm[norm] = t

    def _match_db_tags_in_name(self, product_name: str) -> List[Tag]:
        norm_name = self._normalize_text(product_name)
        return [self._tags_by_norm[n] for n, pat in self._tag_patterns.items() if pat.search(norm_name)]

    def _eligible_by_db_tags(self, product_name: str) -> Tuple[bool, List[Tag]]:
        if not self._tags_norm:
            return (not self.require_db_tag_match, [])
        matched = self._match_db_tags_in_name(product_name)
        return (len(matched) > 0, matched)

    # ================= Logging =================
    def _log_error(self, product_url: str, mensagem: str, etapa: str, product_data: dict, store_info: dict):
        try:
            log = LogColeta(
                product_url=product_url,
                mensagem=(mensagem or "")[:500],
                etapa=etapa,
                status="FALHA",
                input_raw=json.dumps(product_data, ensure_ascii=False) if product_data else None,
                store_info=json.dumps(store_info, ensure_ascii=False) if store_info else None
            )
            self.db.add(log)
            self.db.commit()
        except Exception:
            self.db.rollback()

    # ================= Persistência =================
    def _get_or_create_store(self, seller_id: str, nome_loja: str, seller_score: Optional[int]) -> Optional[LojaConfiavel]:
        loja = self.db.query(LojaConfiavel).filter(LojaConfiavel.id_loja_api == seller_id).first()
        if loja:
            if (seller_score is not None) and isinstance(seller_score, int) and loja.pontuacao_confianca != seller_score:
                try:
                    loja.pontuacao_confianca = seller_score
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            return loja

        try:
            loja = LojaConfiavel(
                nome_loja=nome_loja,
                plataforma="Mercado Livre",
                id_loja_api=seller_id,
                pontuacao_confianca=seller_score if isinstance(seller_score, int) else 3,
                ativa=False
            )
            self.db.add(loja)
            self.db.commit()
            return loja
        except IntegrityError:
            self.db.rollback()
            loja = self.db.query(LojaConfiavel).filter(LojaConfiavel.id_loja_api == seller_id).first()
            if loja:
                return loja
            self.stats["erros"] += 1
            return None
        except Exception:
            self.db.rollback()
            self.stats["erros"] += 1
            return None

    def _create_or_update_product(
        self,
        produto_existente: Optional[Produto],
        item: dict,
        id_product_store: str,
        seller_id: str
    ):
        product_created = False
        if not produto_existente:
            try:
                produto = Produto(
                    url_afiliado_curta=item.get("url_afiliado_curta"),
                    id_product=id_product_store,
                    product_id_loja=seller_id,
                    nome_produto=item["nome_produto"],
                    url_base=item["url_base"],
                    imagem_url=item.get("imagem_url"),
                    ganho_real=item.get("ganho_real"),
                )
                self.db.add(produto)
                self.db.flush()
                self.stats["novo_produto"] += 1
                product_created = True
            except Exception as e:
                self.db.rollback()
                raise RuntimeError(f"Falha criar produto: {e}")
        else:
            produto = produto_existente
            self.stats["produto_existente"] += 1
            if item.get("nome_produto"):
                produto.nome_produto = item["nome_produto"]
            if item.get("imagem_url"):
                produto.imagem_url = item["imagem_url"]
            if item.get("ganho_real") is not None:
                produto.ganho_real = item["ganho_real"]
            if hasattr(produto, "url_afiliado_curta") and not produto.url_afiliado_curta and item.get("url_afiliado_curta"):
                produto.url_afiliado_curta = item["url_afiliado_curta"]
        return produto, product_created

    def _apply_prices_and_dates(self, produto: Produto, item: dict):
        preco_original = item.get("preco_original")
        preco_oferta = item.get("preco_oferta")
        if preco_oferta is not None:
            produto.preco_oferta = float(preco_oferta)
        if preco_original is not None:
            produto.preco_original = float(preco_original) if float(preco_original) > 0 else None
        if produto.preco_original and produto.preco_oferta and produto.preco_original > 0:
            produto.desconto_real = round(100.0 * (1 - (produto.preco_oferta / produto.preco_original)), 2)
        else:
            produto.desconto_real = None

    def _maybe_auto_tag(self, produto: Produto, nome_produto: str):
        if not self.auto_tag_on_collect:
            return
        for tag in self._match_db_tags_in_name(nome_produto):
            if tag not in produto.tags:
                produto.tags.append(tag)

    # ================= Regras de oferta =================
    def _has_open_offer(self, produto_id: int, loja_id: int) -> bool:
        estados_abertos = {"PENDENTE_APROVACAO", "APROVADO", "AGENDADO", "PUBLICADO"}
        return self.db.query(Oferta).filter(
            Oferta.produto_id == produto_id,
            Oferta.loja_id == loja_id,
            Oferta.status.in_(estados_abertos)
        ).first() is not None

    def _check_offer_eligibility(self, loja: LojaConfiavel, produto: Produto, product_created: bool, nome_produto: str) -> Tuple[bool, str]:
        if (loja is None) or (getattr(loja, "ativa", None) not in (True, 1)):
            outcome = "novo_produto_sem_oferta_store_inativa" if product_created else "existente_sem_oferta_store_inativa"
            return False, outcome

        eligible, _ = self._eligible_by_db_tags(nome_produto)
        if not eligible:
            outcome = "novo_produto_sem_oferta_tag_ineligible" if product_created else "existente_sem_oferta_tag_ineligible"
            return False, outcome

        if self._has_open_offer(produto.id, loja.id):
            outcome = "novo_produto_sem_oferta_open_offer" if product_created else "existente_sem_oferta_open_offer"
            return False, outcome

        return True, "ok"

    def _create_offer(self, produto: Produto, loja: LojaConfiavel, product_created: bool) -> Tuple[bool, str]:
        try:
            oferta = Oferta(
                produto_id=produto.id,
                loja_id=loja.id,
                status="PENDENTE_APROVACAO"
            )
            self.db.add(oferta)
            self.db.commit()
            return True, ("novo_produto_oferta_criada" if product_created else "existente_oferta_criada")
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Falha commit oferta: {e}")

    # ================= Entrada única =================
    def process_item(self, item: dict) -> Tuple[bool, str, Optional[bool]]:
        """
        item: dict extraído pelo Collector (somente extração).
        Retorna: (offer_created, outcome_label, product_created)
        Valida todos os campos extraídos; se faltar algum, loga e descarta.
        """
        self.stats["processed_total"] += 1

        # Lista dos campos obrigatórios extraídos pelo collector
        required_fields = [
            "url_base", "id_product", "seller_id", "store_name", "preco_original",
            "preco_oferta", "desconto", "nome_produto", "imagem_url",
            "seller_score", "ganho_real", "url_afiliado_curta"
        ]

        # Validação mínima
        missing = [field for field in required_fields if not item.get(field)]
        if missing:
            self._log_error(
                item.get("url_base"),
                f"Campos ausentes: {', '.join(missing)}",
                "ERRO_VALIDACAO",
                item,
                {field: item.get(field) for field in required_fields}
            )
            self.stats["erros"] += 1
            return (False, "erro_validacao", None)

        url_base = item.get("url_base")
        id_product_store = (item.get("id_product") or "").replace("MLB-", "MLB")
        seller_id = (item.get("seller_id") or "").strip() or None
        nome_loja = (item.get("store_name") or "").strip() or None

        def fail(label: str, msg: str, product_created: Optional[bool] = None):
            # Valida todos os campos novamente e loga apenas os que estão sem valor
            missing_fail = [field for field in required_fields if not item.get(field)]
            self._log_error(
                url_base,
                f"{msg} | Campos ausentes: {', '.join(missing_fail)}" if missing_fail else msg,
                label.upper(),
                item,
                {field: item.get(field) for field in required_fields}
            )
            self.stats["erros"] += 1
            return (False, label, product_created)

        loja = self._get_or_create_store(seller_id, nome_loja, item.get("seller_score"))
        if not loja:
            return fail("erro_criacao_loja", "Loja não pôde ser criada/localizada")

        # Produto
        produto_existente = self.db.query(Produto).filter(Produto.id_product == id_product_store).first()
        try:
            produto, product_created = self._create_or_update_product(produto_existente, item, id_product_store, seller_id)
        except Exception as e:
            return fail("erro_criacao_produto", str(e))

        self._apply_prices_and_dates(produto, item)
        self._maybe_auto_tag(produto, item.get("nome_produto") or "")

        try:
            self.db.commit()
            self.db.refresh(produto)
        except Exception as e:
            self.db.rollback()
            return fail("erro_commit_produto", f"Falha commit produto: {e}", product_created=product_created)

        # Elegibilidade de oferta e criação da oferta
        return self._process_offer_eligibility_and_creation(loja, produto, product_created, item, fail)

    def _process_offer_eligibility_and_creation(self, loja, produto, product_created, item, fail_fn):
        """
        Separa a lógica de elegibilidade de oferta e criação da oferta.
        """
        # Elegibilidade de oferta
        eligible, outcome_or_ok = self._check_offer_eligibility(
            loja, produto, product_created, item.get("nome_produto") or ""
        )
        if not eligible:
            self.stats[outcome_or_ok] = self.stats.get(outcome_or_ok, 0) + 1
            return (False, outcome_or_ok, product_created)

        # Criação da oferta
        try:
            ok, outcome = self._create_offer(produto, loja, product_created)
            self.stats[outcome] = self.stats.get(outcome, 0) + 1
            return (ok, outcome, product_created)
        except Exception as e:
            return fail_fn("erro_commit_oferta", str(e), product_created=product_created)