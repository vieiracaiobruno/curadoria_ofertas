import os
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import func

from backend.models.models import Oferta, HistoricoPreco, Produto

class Validator:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def _get_average_price_last_months(self, produto_id: int, months: int = 3):
        """Calcula o preço médio de um produto nos últimos X meses."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30 * months)

        avg_price = self.db_session.query(func.avg(HistoricoPreco.preco)).\
            filter(HistoricoPreco.produto_id == produto_id).\
            filter(HistoricoPreco.data_verificacao >= start_date).\
            scalar()
        return avg_price if avg_price else 0.0

    def run_validation(self):
        """
        Anota evidências de desconto para ofertas pendentes,
        sem aprovar/rejeitar automaticamente.
        - desconto_real: % vs preço médio (3 meses) ou vs preço original.
        - motivo_validacao: texto curto para aparecer na UI.
        """
        ofertas_pendentes = (
            self.db_session.query(Oferta)
            .filter_by(status="PENDENTE_APROVACAO")
            .all()
        )

        for oferta in ofertas_pendentes:
            produto = self.db_session.get(Produto, oferta.produto_id)
            if not produto:
                oferta.motivo_validacao = "Produto não encontrado no banco."
                # Mantém PENDENTE_APROVACAO para revisão manual
                continue

            # 1) Tenta usar a média dos últimos 3 meses do nosso histórico
            avg_price = self._get_average_price_last_months(produto.id, months=3)
            if avg_price and avg_price > 0:
                calculated_discount = ((avg_price - oferta.preco_oferta) / avg_price) * 100
                oferta.desconto_real = calculated_discount
                oferta.motivo_validacao = (
                    f"Média 3m R$ {avg_price:.2f} · Preço atual R$ {oferta.preco_oferta:.2f} "
                    f"· Δ vs média {calculated_discount:.1f}%"
                )
            else:
                # 2) Sem histórico: registra desconto vs preço original (se houver)
                if oferta.preco_original and oferta.preco_original > 0:
                    desconto_informado = ((oferta.preco_original - oferta.preco_oferta) / oferta.preco_original) * 100
                    oferta.desconto_real = desconto_informado
                    oferta.motivo_validacao = (
                        f"Sem histórico · De R$ {oferta.preco_original:.2f} por R$ {oferta.preco_oferta:.2f} "
                        f"· Desconto informado {desconto_informado:.1f}%"
                    )
                else:
                    oferta.desconto_real = None
                    oferta.motivo_validacao = "Sem histórico e sem preço original · análise manual necessária"

        self.db_session.commit()


if __name__ == "__main__":
    from curadoria_ofertas.backend.db.database import SessionLocal
    db = SessionLocal()
    validator = Validator(db)
    validator.run_validation()
    db.close()


