import os
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import func

from backend.models.models import Oferta, HistoricoPreco, Produto

class Validator:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def _get_average_price_last_months(self, produto_id: int, months: int = 3):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30 * months)
        avg_price = (self.db_session.query(func.avg(HistoricoPreco.preco))
                     .filter(HistoricoPreco.produto_id == produto_id)
                     .filter(HistoricoPreco.data_verificacao >= start_date)
                     .scalar())
        return avg_price if avg_price else 0.0

    def run_validation(self):
        """
        Ajustado: campos de preço/desconto AGORA ficam em Produto.
        Escreve somente motivo_validacao na Oferta e desconto_real no Produto.
        """
        ofertas_pendentes = (
            self.db_session.query(Oferta)
            .filter(Oferta.status == "PENDENTE_APROVACAO")
            .all()
        )

        for oferta in ofertas_pendentes:
            produto = oferta.produto  # relacionamento
            if not produto:
                oferta.motivo_validacao = "Produto não encontrado no banco."
                continue

            if produto.preco_oferta is None:
                oferta.motivo_validacao = "Produto sem preço de oferta para validar."
                continue

            avg_price = self._get_average_price_last_months(produto.id, months=3)

            if avg_price and avg_price > 0:
                calculated_discount = ((avg_price - produto.preco_oferta) / avg_price) * 100
                produto.desconto_real = round(calculated_discount, 2)
                oferta.motivo_validacao = (
                    f"Média 3m R$ {avg_price:.2f} · Preço atual R$ {produto.preco_oferta:.2f} "
                    f"· Δ vs média {calculated_discount:.1f}%"
                )
            else:
                if produto.preco_original and produto.preco_original > 0:
                    desconto_informado = ((produto.preco_original - produto.preco_oferta)
                                          / produto.preco_original) * 100
                    produto.desconto_real = round(desconto_informado, 2)
                    oferta.motivo_validacao = (
                        f"Sem histórico · De R$ {produto.preco_original:.2f} por R$ {produto.preco_oferta:.2f} "
                        f"· Desconto {desconto_informado:.1f}%"
                    )
                else:
                    produto.desconto_real = None
                    oferta.motivo_validacao = "Sem histórico e sem preço original · análise manual"

        self.db_session.commit()

if __name__ == "__main__":
    from backend.db.database import SessionLocal
    db = SessionLocal()
    Validator(db).run_validation()
    db.close()


