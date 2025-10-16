import requests
import os
import json
from sqlalchemy.orm import Session
from datetime import datetime

from backend.models.models import (
    Oferta,
    CanalTelegram,
    Produto,
    LojaConfiavel,
    MetricaOferta,
    OfertaPublicada,
)
from backend.modules.utils.config import get_config

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
            "disable_web_page_preview": False
        }

        # Gerar comando CURL equivalente (para debug)
        curl_command = (
            f"curl -X POST '{url}' "
            f"-H 'Content-Type: application/json' "
            f"-d '{json.dumps(payload, ensure_ascii=False)}'"
        )
        #print("\n[DEBUG] Comando CURL equivalente:")
        #print(curl_command)
        #print("-" * 100)

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                try:
                    err = response.json()
                except Exception:
                    err = response.text
                print(f"Telegram retornou erro {response.status_code}: {err}")
                return False
            return True
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar mensagem para o Telegram ({chat_id}): {e}")
            return False

    def _send_telegram_photo(self, chat_id, photo_url, caption):
        """Envia uma foto com legenda para o Telegram."""
        if not self.telegram_bot_token or self.telegram_bot_token == "SEU_TELEGRAM_BOT_TOKEN":
            print("Telegram Bot Token não configurado. Mensagem não enviada.")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "MarkdownV2"
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                try:
                    err = response.json()
                except Exception:
                    err = response.text
                print(f"Telegram retornou erro {response.status_code}: {err}")
                return False
            return True
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar foto para o Telegram ({chat_id}): {e}")
            return False

    def _publicar_oferta(self, oferta):
        produto = oferta.produto
        loja = oferta.loja

        if not produto or not loja:
            print(f"Produto/Loja ausentes oferta {oferta.id}. Marcando erro.")
            oferta.status = "REJEITADA_ERRO_DADOS"
            return

        long_url = produto.url_afiliado_curta or produto.url_base
        short_url = self._shorten_url(long_url)
        if short_url and (not produto.url_afiliado_curta or produto.url_afiliado_curta != short_url):
            produto.url_afiliado_curta = short_url

        def escape_markdown_v2(text: str) -> str:
            if text is None:
                return ""
            # Escapar somente o necessário (conforme docs Telegram)
            chars = r"_*[]()~`>#+-=|{}.!"""
            for ch in chars:
                text = text.replace(ch, f"\\{ch}")
            return text

        # NÃO escapar a URL (destino do link). Se tiver ')', substituir por %29 para não quebrar o link.
        safe_link_url = (short_url or long_url or "").replace(")", "%29").replace("(", "%28")

        preco_oferta_txt = ""
        preco_original_txt = ""
        desconto_txt = ""

        if produto.preco_oferta is not None:
            preco_oferta_txt = escape_markdown_v2(f"{produto.preco_oferta:.2f}".replace(".", ","))

        if produto.preco_original and produto.preco_original > (produto.preco_oferta or 0):
            preco_original_txt = escape_markdown_v2(f"{produto.preco_original:.2f}".replace(".", ","))

        if produto.desconto_real:
            desconto_txt = escape_markdown_v2(f"{produto.desconto_real:.0f}%")

        message = "*🔥 OFERTA IMPERDÍVEL 🔥*\n\n"
        message += f"*Produto:* {escape_markdown_v2(produto.nome_produto)}\n"
        message += f"*Loja:* {escape_markdown_v2(loja.nome_loja)}\n"
        if preco_original_txt:
            message += f"_De: R$ {preco_original_txt}_\n"
        if preco_oferta_txt:
            message += f"*Preço:* R$ {preco_oferta_txt}\n"
        if desconto_txt:
            message += f"*Desconto:* {desconto_txt}\n"
        # Link: só o texto é escapado
        message += f"\n[🛒 Compre aqui]({safe_link_url})\n"

        tags_do_produto = [t.nome_tag for t in produto.tags]
        if tags_do_produto:
            hashtags = " ".join(["\\#" + escape_markdown_v2(t) for t in tags_do_produto])
            message += "\n" + hashtags

        canais_publicados = set()
        for tag_prod in produto.tags:
            canais = (
                self.db_session.query(CanalTelegram)
                .filter(CanalTelegram.tags.any(id=tag_prod.id))
                .filter(CanalTelegram.ativo == True)
                .all()
            )
            for canal in canais:
                chat_id = canal.id_canal_api
                if chat_id in canais_publicados:
                    continue
                print(f"Publicando oferta {oferta.id} no canal {canal.nome_amigavel} ({chat_id})...")
                
                # Tenta enviar com imagem, se disponível
                sucesso = False
                if produto.imagem_url:
                    sucesso = self._send_telegram_photo(chat_id, produto.imagem_url, message)
                    if not sucesso:
                        print(f"Falha ao enviar foto, tentando mensagem de texto...")
                        sucesso = self._send_telegram_message(chat_id, message)
                else:
                    sucesso = self._send_telegram_message(chat_id, message)
                
                if sucesso:
                    canais_publicados.add(chat_id)
                    print(f"Publicado no canal {canal.nome_amigavel}.")
                    
                    # Salva registro de OfertaPublicada com snapshot dos dados
                    oferta_publicada = OfertaPublicada(
                        oferta_id=oferta.id,
                        canal_id=canal.id,
                        data_publicacao=datetime.now(),
                        nome_produto=produto.nome_produto,
                        preco_original=produto.preco_original,
                        preco_oferta=produto.preco_oferta,
                        desconto_real=produto.desconto_real,
                        url_afiliado_curta=short_url or long_url,
                        imagem_url=produto.imagem_url,
                        nome_loja=loja.nome_loja,
                        canal_nome=canal.nome_amigavel
                    )
                    self.db_session.add(oferta_publicada)
                else:
                    print(f"Falha ao publicar no canal {canal.nome_amigavel}.")

        if canais_publicados:
            oferta.status = "PUBLICADO"
            oferta.data_publicacao = datetime.now()
            metrica = MetricaOferta(oferta_id=oferta.id, cliques=0, vendas=0)
            self.db_session.add(metrica)
        else:
            oferta.status = "REJEITADA_SEM_CANAL"
            print(f"Oferta {oferta.id} não publicada: nenhum canal apto.")

    def publicar_oferta_individual(self, oferta):
        """
        Publica uma única oferta aprovada no Telegram.
        Método público para uso externo.
        
        Args:
            oferta: Instância de Oferta a ser publicada
        """
        self._publicar_oferta(oferta)

    def run_publication(self):
        """
        Publica ofertas aprovadas. Ajustado para usar campos de preço em Produto.
        Salva link curto em produto.url_afiliado_curta.
        """
        ofertas_para_publicar = (
            self.db_session.query(Oferta)
            .filter(Oferta.status == "APROVADO")
            .all()
        )

        for oferta in ofertas_para_publicar:
            self._publicar_oferta(oferta)

        self.db_session.commit()

if __name__ == "__main__":
    from backend.db.database import SessionLocal
    db = SessionLocal()
    Publisher(db).run_publication()
    db.close()


