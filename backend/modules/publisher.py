import requests
import os
from sqlalchemy.orm import Session
from datetime import datetime

from backend.models.models import Oferta, CanalTelegram, Produto, LojaConfiavel, MetricaOferta
from backend.utils.config import get_config

class Publisher:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        #self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        #self.telegram_bot_token = "SEU_TELEGRAM_BOT_TOKEN" # Substitua pelo seu token real
        #self.bitly_api_key = "SEU_BITLY_API_KEY" # Substitua pela sua API Key real
        self.telegram_bot_token = get_config("TELEGRAM_BOT_TOKEN")
        # Unificado: Bitly agora usa SEMPRE o Access Token (GAT/OAuth)
        self.bitly_access_token = get_config("BITLY_ACCESS_TOKEN")

    def _shorten_url(self, long_url):
        """Encurta uma URL usando a API do Bitly."""
        #if not self.bitly_api_key or self.bitly_api_key == "SEU_BITLY_API_KEY":
        #    print("Bitly API Key não configurada. Usando URL longa.")
        if not self.bitly_access_token or self.bitly_access_token.strip().upper() in {"SEU_BITLY_API_KEY","SEU_BITLY_ACCESS_TOKEN"}:
            print("Bitly Access Token não configurado. Usando URL longa.")
            return long_url

        headers = {
            "Authorization": f"Bearer {self.bitly_access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "long_url": long_url
        }
        try:
            response = requests.post("https://api-ssl.bitly.com/v4/shorten", headers=headers, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()
            return data["link"]
        except requests.exceptions.RequestException as e:
            print(f"Erro ao encurtar URL com Bitly: {e}")
            return long_url

    def _send_telegram_message(self, chat_id, message_text):
        """Envia uma mensagem para o Telegram."""
        if not self.telegram_bot_token or self.telegram_bot_token == "SEU_TELEGRAM_BOT_TOKEN":
            print("Telegram Bot Token não configurado. Mensagem não enviada.")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False # Permite pré-visualização do link
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar mensagem para o Telegram ({chat_id}): {e}")
            return False

    def run_publication(self):
        """Publica ofertas aprovadas para curadoria nos canais do Telegram."""
        # Se você aprova com "APROVADO" na API, use esse status:
        ofertas_para_publicar = (
            self.db_session.query(Oferta)
            .filter(Oferta.status == "APROVADO")  # antes: "APROVADA_PARA_CURADORIA"
            .all()
        )

        for oferta in ofertas_para_publicar:
            produto = self.db_session.get(Produto, oferta.produto_id)
            loja = self.db_session.get(LojaConfiavel, oferta.loja_id)

            if not produto or not loja:
                print(f"Produto ou Loja não encontrados para oferta {oferta.id}. Pulando.")
                oferta.status = "REJEITADA_ERRO_DADOS"
                continue

            short_url = self._shorten_url(oferta.url_afiliado_longa)

            def escape_markdown_v2(text):
                if text is None:
                    return ""
                chars_to_escape = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
                for char in chars_to_escape:
                    text = text.replace(char, f"\\{char}")
                return text

            produto_nome_escaped = escape_markdown_v2(produto.nome_produto)
            loja_nome_escaped = escape_markdown_v2(loja.nome_loja)
            preco_oferta_escaped = escape_markdown_v2(f"{oferta.preco_oferta:.2f}".replace(".", ","))
            preco_original_escaped = escape_markdown_v2(f"{oferta.preco_original:.2f}".replace(".", ",")) if oferta.preco_original else ""
            desconto_escaped = escape_markdown_v2(f"{oferta.desconto_real:.0f}%") if oferta.desconto_real else ""

            message = "*🔥 OFERTA IMPERDÍVEL 🔥*\n\n"
            message += f"*Produto:* {produto_nome_escaped}\n"
            message += f"*Loja:* {loja_nome_escaped}\n"
            message += f"*Preço:* R$ {preco_oferta_escaped}\n"
            if oferta.preco_original and oferta.preco_original > oferta.preco_oferta:
                message += f"_De: R$ {preco_original_escaped}_ \n"
            if oferta.desconto_real:
                message += f"*Desconto:* {desconto_escaped}\n"
            message += f"\n[🛒 Compre aqui]({escape_markdown_v2(short_url)})\n"

            # --- FIX do SyntaxWarning: use "\\#" em vez de "\#" ---
            tags_do_produto = [tag.nome_tag for tag in produto.tags]
            if tags_do_produto:
                hashtags = " ".join(["\\#" + escape_markdown_v2(t) for t in tags_do_produto])
                message += "\n" + hashtags

            # Publicar nos canais relevantes
            canais_publicados = []
            for tag_produto in produto.tags:
                canais_por_tag = (
                    self.db_session.query(CanalTelegram)
                    .filter(CanalTelegram.tags.any(id=tag_produto.id))
                    .filter(CanalTelegram.ativo == True)
                    .all()
                )

                for canal in canais_por_tag:
                    # Use campos do seu modelo: id_canal_api (chat_id) e nome_amigavel
                    chat_id = canal.id_canal_api
                    nome_canal = canal.nome_amigavel
                    if chat_id not in canais_publicados:
                        print(f"Tentando publicar oferta {oferta.id} no canal {nome_canal} ({chat_id})...")
                        if self._send_telegram_message(chat_id, message):
                            canais_publicados.append(chat_id)
                            print(f"Oferta {oferta.id} publicada com sucesso no canal {nome_canal}.")
                        else:
                            print(f"Falha ao publicar oferta {oferta.id} no canal {nome_canal}.")

            if canais_publicados:
                oferta.status = "PUBLICADO"
                oferta.data_publicacao = datetime.now()
                oferta.url_afiliado_curta = short_url  # antes: url_publicada (campo não existe)
                # MetricaOferta não tem 'conversao' no modelo
                metrica = MetricaOferta(oferta_id=oferta.id, cliques=0, vendas=0)
                self.db_session.add(metrica)
            else:
                oferta.status = "REJEITADA_SEM_CANAL"
                print(f"Oferta {oferta.id} não publicada: nenhum canal relevante encontrado ou falha no envio.")

        self.db_session.commit()

if __name__ == "__main__":
    from curadoria_ofertas.backend.db.database import SessionLocal
    db = SessionLocal()
    publisher = Publisher(db)
    publisher.run_publication()
    db.close()


