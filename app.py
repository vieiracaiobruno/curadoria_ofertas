import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from datetime import datetime
from dotenv import load_dotenv
import ssl

# Carrega .env
load_dotenv('config.env')

# DB e Models (use SEMPRE os objetos do database.py)
from backend.db.database import SessionLocal, engine, create_db_tables
from backend.models.models import Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, LogColeta
from sqlalchemy.orm import joinedload, selectinload
import unicodedata, re

from backend.modules.utils.config import get_config
from sqlalchemy import or_

# Garantir as tabelas uma ÚNICA vez, usando o bootstrap centralizado do database.py
create_db_tables()

app = Flask(__name__, template_folder='./frontend/templates', static_folder='./frontend/static')
#app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "sua_chave_secreta_aqui_para_producao")
app.config["SECRET_KEY"] = get_config("SECRET_KEY", "sua_chave_secreta_aqui_para_producao")  # :contentReference[oaicite:10]{index=10}

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)

def _compile_pat(token: str):
    if len(token) <= 3 and re.fullmatch(r"[a-z0-9]+", token or ""):
        return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.I)
    return re.compile(re.escape(token), re.I)

@app.route("/lojas-confiaveis")
def lojas_confiaveis():
    with SessionLocal() as db:
        lojas = db.query(LojaConfiavel).order_by(LojaConfiavel.nome_loja).all()
    return render_template("lojas_confiaveis.html", lojas=lojas)

@app.route("/")
@app.route("/dashboard")
def dashboard():
    with SessionLocal() as db:
        ofertas = (
            db.query(Oferta)
              .options(
                  joinedload(Oferta.produto).selectinload(Produto.tags),
                  joinedload(Oferta.loja),
              )
              .filter(Oferta.status == "PENDENTE_APROVACAO")
              .all()
        )
        todas_tags = db.query(Tag).order_by(Tag.nome_tag).all()

        # pré-compila padrões das tags
        pats = []
        for t in todas_tags:
            nt = _norm(t.nome_tag)
            if not nt: continue
            pats.append((t, _compile_pat(nt)))

        # anota no objeto uma lista de tags "filtradas" (só para a view)
        for of in ofertas:
            name_norm = _norm(of.produto.nome_produto)
            matched = [t for t, pat in pats if pat.search(name_norm)]
            of._prefilter_tags = matched  # atributo ad-hoc para a view

    return render_template("fila_aprovacao.html",
                           ofertas=ofertas,
                           todas_tags=todas_tags)

@app.route("/publicadas")
@app.route("/ofertas/publicadas")
def ofertas_publicadas():
    from backend.models.models import OfertaPublicada
    with SessionLocal() as db:
        # Busca os registros de OfertaPublicada que contêm snapshot dos dados
        ofertas_publicadas = (
            db.query(OfertaPublicada)
              .options(
                  joinedload(OfertaPublicada.oferta).selectinload(Oferta.produto).selectinload(Produto.tags),
                  joinedload(OfertaPublicada.canal)
              )
              .order_by(OfertaPublicada.data_publicacao.desc())
              .all()
        )
        
        # Agrupa por oferta_id para mostrar todos os canais
        from collections import defaultdict
        canais_por_oferta = defaultdict(list)
        ofertas_dict = {}
        for op in ofertas_publicadas:
            canais_por_oferta[op.oferta_id].append(op.canal_nome or (op.canal.nome_amigavel if op.canal else "—"))
            if op.oferta_id not in ofertas_dict:
                ofertas_dict[op.oferta_id] = op
        
        # Lista única de ofertas publicadas
        ofertas_unicas = list(ofertas_dict.values())
        
    return render_template("ofertas_publicadas.html", 
                         ofertas=ofertas_unicas, 
                         canais_por_oferta=dict(canais_por_oferta))

@app.route("/configuracoes")
def configuracoes():
    with SessionLocal() as db:
        tags = db.query(Tag).all()
        canais = (db.query(CanalTelegram)
                    .options(joinedload(CanalTelegram.tags))
                    .all())
    return render_template("configuracoes.html", tags=tags, canais=canais)

# Registrar blueprint da API
from backend.routes.api import api_bp
app.register_blueprint(api_bp, url_prefix="/api")

@app.route("/produtos")
def lista_produtos():
    from datetime import timedelta
    with SessionLocal() as db:
        produtos = (
            db.query(Produto)
              .options(
                  selectinload(Produto.tags),
                  selectinload(Produto.historico_precos),
                  selectinload(Produto.ofertas),
              )
              .all()
        )

        # Coleta os IDs de loja existentes nos produtos
        seller_ids = {p.product_id_loja for p in produtos if getattr(p, "product_id_loja", None)}
        alt_ids    = {getattr(p, "product_id_loja_alt", None) for p in produtos if getattr(p, "product_id_loja_alt", None)}

        by_seller, by_alt = {}, {}
        if seller_ids or alt_ids:
            lojas = (
                db.query(LojaConfiavel)
                  .filter(
                      or_(
                          LojaConfiavel.id_loja_api.in_(seller_ids) if seller_ids else False,
                          LojaConfiavel.id_loja_api_alt.in_(alt_ids) if alt_ids else False,
                      )
                  )
                  .all()
            )
            by_seller = {l.id_loja_api: l.nome_loja for l in lojas if getattr(l, "id_loja_api", None)}
            by_alt    = {l.id_loja_api_alt: l.nome_loja for l in lojas if getattr(l, "id_loja_api_alt", None)}

        # Anota nome da loja (se encontrado) sem depender da tabela no template
        for p in produtos:
            p._nome_loja = by_seller.get(getattr(p, "product_id_loja", None)) \
                           or by_alt.get(getattr(p, "product_id_loja_alt", None))
            
            # Requirement 6: Marca se produto já foi postado
            p._foi_postado = any(oferta.status == "PUBLICADO" for oferta in p.ofertas)
            
            # Requirement 7: Marca se produto está na fila de aprovação
            p._na_fila = any(oferta.status == "PENDENTE_APROVACAO" for oferta in p.ofertas)
            
            # Requirement 8: Marca se produto é novo ou foi atualizado recentemente (1 dia)
            agora = datetime.now()
            p._e_novo = False
            p._foi_atualizado = False
            if getattr(p, "data_criacao", None):
                diferenca_criacao = agora - p.data_criacao
                if diferenca_criacao <= timedelta(days=1):
                    p._e_novo = True
            if getattr(p, "data_atualizacao", None):
                diferenca_atualizacao = agora - p.data_atualizacao
                # Só marca como atualizado se não for novo
                if diferenca_atualizacao <= timedelta(days=1) and not p._e_novo:
                    p._foi_atualizado = True
            
            # Requirement 4: Verifica se loja está ativa
            loja = None
            if p.product_id_loja:
                loja = db.query(LojaConfiavel).filter(LojaConfiavel.id_loja_api == p.product_id_loja).first()
            p._loja_ativa = loja.ativa if loja else False

    return render_template("produtos.html", produtos=produtos)

@app.route("/variaveis")
def variaveis():
    return render_template("env_vars.html")

from zoneinfo import ZoneInfo
from datetime import datetime
from datetime import timezone, timedelta

@app.route("/logs")
def view_logs():
    with SessionLocal() as db:
        logs = (
            db.query(LogColeta)
              .order_by(LogColeta.id.desc())
              .limit(200)
              .all()
        )

        # Converte UTC -> America/Sao_Paulo com fallbacks
        # Tenta ZoneInfo; se indisponível, tenta dateutil; por fim usa offset fixo (-03:00)
        try:
            tz_utc = ZoneInfo("UTC")
            tz_sp = ZoneInfo("America/Sao_Paulo")
        except Exception:
            try:
                from dateutil import tz as dateutil_tz
                tz_utc = dateutil_tz.gettz("UTC") or timezone.utc
                tz_sp = dateutil_tz.gettz("America/Sao_Paulo")
            except Exception:
                tz_utc = timezone.utc
                tz_sp = timezone(timedelta(hours=-3))  # fallback sem DST

        for log in logs:
            if not log.criado_em:
                continue
            dt = log.criado_em
            if dt.tzinfo is None:
                # assume que está salvo em UTC
                dt = dt.replace(tzinfo=tz_utc)
            try:
                dt = dt.astimezone(tz_sp)
            except Exception:
                # fallback final: mantém UTC
                dt = dt.astimezone(timezone.utc)
            log.criado_em = dt

    return render_template("logs_coleta.html", logs=logs)


if __name__ == "__main__":
    # Garante tabelas
    create_db_tables()

    debug_flag = (get_config("FLASK_DEBUG", "True") or "True").lower() == "true"

    app.run(
        debug=debug_flag,
        host="0.0.0.0",
        port=int(get_config("PORT", "5000"))
    )
