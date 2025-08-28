from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import func

from curadoria_ofertas.backend.models.models import Oferta, HistoricoPreco, Produto

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
        """Valida as ofertas pendentes de aprovação."""
        ofertas_pendentes = self.db_session.query(Oferta).filter_by(status="PENDENTE_APROVACAO").all()

        for oferta in ofertas_pendentes:
            produto = self.db_session.query(Produto).get(oferta.produto_id)
            if not produto:
                oferta.status = "REJEITADA_PRODUTO_NAO_ENCONTRADO"
                continue

            # 1. Validação de Desconto Real (10% em relação ao preço médio)
            avg_price = self._get_average_price_last_months(produto.id)
            if avg_price > 0:
                calculated_discount = ((avg_price - oferta.preco_oferta) / avg_price) * 100
                if calculated_discount >= 10:
                    oferta.desconto_real = calculated_discount
                    oferta.status = "APROVADA_PARA_CURADORIA"
                    print(f"Oferta {oferta.id} ({produto.nome_produto}) aprovada para curadoria (desconto real: {calculated_discount:.2f}%).")
                else:
                    oferta.status = "REJEITADA_DESCONTO_INSUFICIENTE"
                    print(f"Oferta {oferta.id} ({produto.nome_produto}) rejeitada (desconto real: {calculated_discount:.2f}% < 10%).")
            else:
                # Se não há histórico de preço, aprova para curadoria com base no desconto informado
                if oferta.desconto >= 10:
                    oferta.status = "APROVADA_PARA_CURADORIA"
                    oferta.desconto_real = oferta.desconto
                    print(f"Oferta {oferta.id} ({produto.nome_produto}) aprovada para curadoria (sem histórico, desconto informado: {oferta.desconto:.2f}%).")
                else:
                    oferta.status = "REJEITADA_DESCONTO_INSUFICIENTE"
                    print(f"Oferta {oferta.id} ({produto.nome_produto}) rejeitada (sem histórico, desconto informado: {oferta.desconto:.2f}% < 10%).")

            # 2. Tratamento de Duplicidade (ofertar o menor preço)
            # Se houver outras ofertas para o mesmo produto já aprovadas para curadoria,
            # mantenha apenas a de menor preço e rejeite as outras.
            ofertas_existentes_aprovadas = self.db_session.query(Oferta).\
                filter(Oferta.produto_id == oferta.produto_id).\
                filter(Oferta.status == "APROVADA_PARA_CURADORIA").\
                filter(Oferta.id != oferta.id).\
                all()
            
            if ofertas_existentes_aprovadas:
                # Encontra a oferta de menor preço entre as aprovadas e a atual
                all_relevant_offers = [oferta] + ofertas_existentes_aprovadas
                best_offer = min(all_relevant_offers, key=lambda o: o.preco_oferta)

                for o in all_relevant_offers:
                    if o.id == best_offer.id:
                        o.status = "APROVADA_PARA_CURADORIA" # Garante que a melhor oferta permaneça aprovada
                    else:
                        o.status = "REJEITADA_DUPLICIDADE" # Rejeita as outras
                        print(f"Oferta {o.id} ({produto.nome_produto}) rejeitada por duplicidade (preço maior).")

        self.db_session.commit()

if __name__ == "__main__":
    from curadoria_ofertas.backend.db.database import SessionLocal
    db = SessionLocal()
    validator = Validator(db)
    validator.run_validation()
    db.close()


