from flask import Blueprint, request, jsonify
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime

from ..db.database import DATABASE_URL, Base, SessionLocal
from ..models.models import Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta, OfertaPublicada, HistoricoPreco, ConfigVar
from backend.utils.config import get_config, set_config, list_configs

api_bp = Blueprint("api", __name__)

# ---------------------------
# Helpers
# ---------------------------

def _normalize_tag_name(name: str) -> str:
    """normaliza um nome de tag vindo do front (#opcional, trim, lower)."""
    if name is None:
        return ""
    s = name.replace("#", "").strip().lower()
    return s

def _resolve_tags_by_names(db, names):
    """
    Recebe lista de strings (nomes de tags), normaliza, remove duplicatas,
    busca/cria Tag e retorna a lista de instâncias Tag pronta para associar.
    """
    if not names:
        return []

    norm_unique = []
    seen = set()
    for n in names:
        s = _normalize_tag_name(n)
        if s and s not in seen:
            seen.add(s)
            norm_unique.append(s)

    resolved = []
    if not norm_unique:
        return resolved

    # busca as que já existem
    existentes = db.query(Tag).filter(Tag.nome_tag.in_(norm_unique)).all()
    by_name = {t.nome_tag: t for t in existentes}

    # cria as que faltam
    for nome in norm_unique:
        if nome not in by_name:
            t = Tag(nome_tag=nome)
            db.add(t)
            db.flush()  # garante id para a N:N
            by_name[nome] = t

    # mantém a ordem normalizada
    for nome in norm_unique:
        resolved.append(by_name[nome])

    return resolved

# Helper para obter a sessão do DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Canais por tags (consulta)
# ---------------------------
@api_bp.route("/canais_destino", methods=["GET"])
def get_canais_destino():
    tags_str = request.args.get("tags", "")
    # normaliza lista de nomes
    tags_list = [_normalize_tag_name(t) for t in tags_str.split(",") if _normalize_tag_name(t)]

    db = SessionLocal()
    canais_encontrados = []
    if tags_list:
        # Busca tags por nome normalizado
        tags_obj = db.query(Tag).filter(Tag.nome_tag.in_(tags_list)).all()
        tag_ids = [tag.id for tag in tags_obj]

        if tag_ids:
            # Canais ativos que tenham ALGUMA das tags (distinct p/ evitar duplicados)
            canais_encontrados = (
                db.query(CanalTelegram)
                  .join(CanalTelegram.tags)
                  .filter(CanalTelegram.ativo == True, Tag.id.in_(tag_ids))
                  .distinct()
                  .all()
            )

    db.close()

    canais_data = [{
        "id": canal.id,
        "nome_amigavel": canal.nome_amigavel,
        "id_canal_api": canal.id_canal_api
    } for canal in canais_encontrados]

    return jsonify({"status": "success", "canais": canais_data}), 200

# ---------------------------
# Aprovar / Rejeitar / Agendar oferta
# ---------------------------
@api_bp.route("/ofertas/<int:oferta_id>/aprovar", methods=["POST"])
def api_aprovar_oferta(oferta_id):
    db = SessionLocal()
    oferta = db.get(Oferta, oferta_id)
    if not oferta:
        db.close()
        return jsonify({"status": "error", "message": "Oferta não encontrada."}), 404

    try:
        # Atualiza as tags do produto se forem enviadas
        tags_from_frontend = request.json.get("tags", [])
        produto = db.get(Produto, oferta.produto_id)
        if produto is not None and tags_from_frontend is not None:  # permite [] para remover todas
            produto.tags.clear()
            produto.tags.extend(_resolve_tags_by_names(db, tags_from_frontend))

        oferta.status = "APROVADO"
        db.commit()
        return jsonify({"status": "success", "message": "Oferta aprovada com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.route("/ofertas/<int:oferta_id>/rejeitar", methods=["POST"])
def api_rejeitar_oferta(oferta_id):
    db = SessionLocal()
    oferta = db.get(Oferta, oferta_id)
    if not oferta:
        db.close()
        return jsonify({"status": "error", "message": "Oferta não encontrada."}), 404

    try:
        oferta.status = "REJEITADO"
        db.commit()
        return jsonify({"status": "success", "message": "Oferta rejeitada com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.route("/ofertas/<int:oferta_id>/agendar", methods=["POST"])
def api_agendar_oferta(oferta_id):
    db = SessionLocal()
    oferta = db.get(Oferta, oferta_id)
    if not oferta:
        db.close()
        return jsonify({"status": "error", "message": "Oferta não encontrada."}), 404

    data_agendamento_str = request.json.get("data_agendamento")
    if not data_agendamento_str:
        db.close()
        return jsonify({"status": "error", "message": "Data de agendamento é obrigatória."}), 400

    try:
        data_agendamento = datetime.fromisoformat(data_agendamento_str)
    except ValueError:
        db.close()
        return jsonify({"status": "error", "message": "Formato de data inválido."}), 400

    try:
        oferta.status = "AGENDADO"
        oferta.data_publicacao = data_agendamento
        db.commit()
        return jsonify({"status": "success", "message": "Oferta agendada com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# ---------------------------
# Lojas Confiáveis (CRUD)
# ---------------------------
@api_bp.route("/lojas", methods=["POST"])
def api_add_loja():
    db = SessionLocal()
    data = request.json or {}
    try:
        loja = LojaConfiavel(
            nome_loja=(data.get("nome_loja") or "").strip(),
            plataforma=(data.get("plataforma") or "Mercado Livre").strip(),
            id_loja_api=(data.get("id_loja_api") or "").strip(),
            # se seu modelo já tiver a coluna extra, trate aqui; se não tiver, ignore esta linha
            id_loja_api_alt=(data.get("id_loja_api_alt") or "").strip() or None,
            pontuacao_confianca=int(data.get("pontuacao_confianca", 3)),
            ativa=bool(data.get("ativa", True)),
        )
        if not loja.nome_loja or not loja.plataforma:
            return jsonify({"status": "error", "message": "nome_loja e plataforma são obrigatórios."}), 400

        db.add(loja)
        db.commit()
        return jsonify({"status": "success", "message": "Loja adicionada com sucesso!", "id": loja.id}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        db.close()

@api_bp.route("/lojas/<int:loja_id>", methods=["PUT"])
def api_update_loja(loja_id):
    db = SessionLocal()
    loja = db.get(LojaConfiavel, loja_id)
    if not loja:
        db.close()
        return jsonify({"status": "error", "message": "Loja não encontrada."}), 404

    data = request.json
    try:
        loja.nome_loja = data.get("nome_loja", loja.nome_loja)
        loja.plataforma = data.get("plataforma", loja.plataforma)
        loja.id_loja_api = data.get("id_loja_api", loja.id_loja_api)
        loja.pontuacao_confianca = data.get("pontuacao_confianca", loja.pontuacao_confianca)
        loja.ativa = data.get("ativa", loja.ativa)
        db.commit()
        return jsonify({"status": "success", "message": "Loja atualizada com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.route("/lojas/<int:loja_id>", methods=["DELETE"])
def api_delete_loja(loja_id):
    db = SessionLocal()
    loja = db.get(LojaConfiavel, loja_id)
    if not loja:
        db.close()
        return jsonify({"status": "error", "message": "Loja não encontrada."}), 404

    try:
        db.delete(loja)
        db.commit()
        return jsonify({"status": "success", "message": "Loja removida com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# ---------------------------
# Tags (CRUD)
# ---------------------------
@api_bp.route("/tags", methods=["POST"])
def api_add_tag():
    db = SessionLocal()
    data = request.json
    try:
        tag_name = _normalize_tag_name(data.get("nome_tag", ""))
        if not tag_name:
            return jsonify({"status": "error", "message": "nome_tag é obrigatório."}), 400

        existing_tag = db.query(Tag).filter_by(nome_tag=tag_name).first()
        if existing_tag:
            return jsonify({"status": "error", "message": "Tag já existe."}), 409

        tag = Tag(nome_tag=tag_name)
        db.add(tag)
        db.commit()
        return jsonify({"status": "success", "message": "Tag adicionada com sucesso!", "id": tag.id}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        db.close()

@api_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def api_delete_tag(tag_id):
    db = SessionLocal()
    tag = db.get(Tag, tag_id)
    if not tag:
        db.close()
        return jsonify({"status": "error", "message": "Tag não encontrada."}), 404

    try:
        db.delete(tag)
        db.commit()
        return jsonify({"status": "success", "message": "Tag removida com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# ---------------------------
# Canais Telegram (CRUD)
# ---------------------------
@api_bp.route("/canais", methods=["POST"])
def api_add_canal():
    db = SessionLocal()
    data = request.json
    try:
        canal = CanalTelegram(
            nome_amigavel=(data.get("nome_amigavel") or "").strip(),
            id_canal_api=(data.get("id_canal_api") or "").strip(),
            inscritos=int(data.get("inscritos", 0) or 0),
            ativo=bool(data.get("ativo", True))
        )
        if not canal.nome_amigavel or not canal.id_canal_api:
            return jsonify({"status": "error", "message": "nome_amigavel e id_canal_api são obrigatórios."}), 400

        db.add(canal)
        db.flush()  # obter ID antes de associar tags

        # Resolve/associa tags por NOME (contrato: array de strings)
        tags_associadas = data.get("tags_associadas", [])
        canal.tags = _resolve_tags_by_names(db, tags_associadas)

        db.commit()
        return jsonify({"status": "success", "message": "Canal adicionado com sucesso!", "id": canal.id}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        db.close()

@api_bp.route("/canais/<int:canal_id>", methods=["PUT"])
def api_update_canal(canal_id):
    db = SessionLocal()
    canal = db.get(CanalTelegram, canal_id)
    if not canal:
        db.close()
        return jsonify({"status": "error", "message": "Canal não encontrado."}), 404

    data = request.json
    try:
        if "nome_amigavel" in data:
            novo = (data.get("nome_amigavel") or "").strip()
            if novo:
                canal.nome_amigavel = novo
        if "id_canal_api" in data:
            novo = (data.get("id_canal_api") or "").strip()
            if not novo:
                return jsonify({"status": "error", "message": "id_canal_api não pode ser vazio."}), 400
            canal.id_canal_api = novo
        if "inscritos" in data:
            canal.inscritos = int(data.get("inscritos") or 0)
        if "ativo" in data:
            canal.ativo = bool(data.get("ativo"))

        # Substituição total das tags quando o campo vier presente
        if "tags_associadas" in data:
            canal.tags = _resolve_tags_by_names(db, data.get("tags_associadas"))

        db.commit()
        return jsonify({"status": "success", "message": "Canal atualizado com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.route("/canais/<int:canal_id>", methods=["DELETE"])
def api_delete_canal(canal_id):
    db = SessionLocal()
    canal = db.get(CanalTelegram, canal_id)
    if not canal:
        db.close()
        return jsonify({"status": "error", "message": "Canal não encontrado."}), 404

    try:
        db.delete(canal)
        db.commit()
        return jsonify({"status": "success", "message": "Canal removido com sucesso!"}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.delete("/produtos/<int:produto_id>")
def api_delete_produto(produto_id: int):
    db = SessionLocal()
    try:
        produto = db.get(Produto, produto_id)
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado"}), 404

        # 1) Apaga métricas e publicações das ofertas do produto
        ofertas = db.query(Oferta).filter(Oferta.produto_id == produto_id).all()
        if ofertas:
            oferta_ids = [o.id for o in ofertas]
            db.query(MetricaOferta).filter(MetricaOferta.oferta_id.in_(oferta_ids)).delete(synchronize_session=False)
            db.query(OfertaPublicada).filter(OfertaPublicada.oferta_id.in_(oferta_ids)).delete(synchronize_session=False)
            # 2) Apaga as ofertas
            db.query(Oferta).filter(Oferta.id.in_(oferta_ids)).delete(synchronize_session=False)

        # 3) Apaga histórico de preços
        db.query(HistoricoPreco).filter(HistoricoPreco.produto_id == produto_id).delete(synchronize_session=False)

        # 4) Limpa vínculo N:N com tags e apaga o produto
        produto.tags.clear()
        db.flush()
        db.delete(produto)

        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.get("/env")
def api_list_env():
    rows = list_configs()
    data = []
    for r in rows:
        data.append({
            "id": r.id,
            "key": r.key,
            "value": None if r.is_secret else r.value,  # mascara segredos
            "is_secret": r.is_secret,
            "description": r.description,
            "updated_at": r.updated_at.isoformat()
        })
    return jsonify({"status":"success", "items":data})

@api_bp.post("/env")
def api_create_env():
    payload = request.json or {}
    key = (payload.get("key") or "").strip()
    value = payload.get("value")
    is_secret = bool(payload.get("is_secret", True))
    description = payload.get("description")
    if not key:
        return jsonify({"status":"error","message":"key é obrigatório"}), 400
    row = set_config(key, value, is_secret=is_secret, description=description)
    return jsonify({"status":"success","id":row.id}), 201

@api_bp.put("/env/<int:cfg_id>")
def api_update_env(cfg_id: int):
    from backend.db.database import SessionLocal
    with SessionLocal() as db:
        row = db.get(ConfigVar, cfg_id)
        if not row:
            return jsonify({"status":"error","message":"Config não encontrada"}), 404
        payload = request.json or {}
        if "key" in payload:
            new_key = (payload.get("key") or "").strip()
            if not new_key:
                return jsonify({"status":"error","message":"key não pode ser vazio"}), 400
            row.key = new_key
        if "value" in payload:
            row.value = payload.get("value")
        if "is_secret" in payload:
            row.is_secret = bool(payload.get("is_secret"))
        if "description" in payload:
            row.description = payload.get("description")
        row.updated_at = datetime.now()
        db.commit()
    return jsonify({"status":"success"})

@api_bp.delete("/env/<int:cfg_id>")
def api_delete_env(cfg_id: int):
    from backend.db.database import SessionLocal
    with SessionLocal() as db:
        row = db.get(ConfigVar, cfg_id)
        if not row:
            return jsonify({"status":"error","message":"Config não encontrada"}), 404
        db.delete(row)
        db.commit()
    return jsonify({"status":"success"})

@api_bp.route("/lojas/auto_from_produto/<int:produto_id>", methods=["POST"])
def api_auto_create_loja_from_produto(produto_id):
    """
    Dado um produto (com url_base), resolve MLB-XXXX, tenta achar loja por id alternativo
    e, se não existir, abre a página e cria a LojaConfiavel automaticamente.
    """
    from backend.modules.collector import Collector  # reusar lógica
    db = SessionLocal()
    try:
        produto = db.get(Produto, produto_id)
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        col = Collector(db)  # usa o mesmo BrowserManager/cookies
        loja, alt = col._resolve_store_by_alt_or_scrape(produto.url_base)
        col.browser.close()

        if not loja:
            return jsonify({"status": "error", "message": "Não foi possível identificar a loja pelo link do produto."}), 422

        # grava alt no produto se ainda não tem
        if alt and not produto.product_id_loja_alt:
            produto.product_id_loja_alt = alt
            db.commit()

        data = {
            "id": loja.id,
            "nome_loja": loja.nome_loja,
            "plataforma": loja.plataforma,
            "id_loja_api": loja.id_loja_api,
            "id_loja_api_alt": loja.id_loja_api_alt
        }
        return jsonify({"status": "success", "message": "Loja resolvida/registrada com sucesso.", "loja": data}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@api_bp.route("/tags", methods=["GET"])
def api_list_tags():
    db = SessionLocal()
    try:
        tags = db.query(Tag).order_by(Tag.nome_tag.asc()).all()
        return jsonify({"status": "success", "tags": [t.nome_tag for t in tags]}), 200
    finally:
        db.close()

@api_bp.route("/produtos/<int:produto_id>/tags", methods=["POST"])
def api_add_tags_to_product(produto_id):
    """
    Associa tags EXISTENTES por nome ao produto. Não cria tags novas aqui.
    body: {"tags": ["informatica","gamer"]}
    """
    db = SessionLocal()
    try:
        produto = db.get(Produto, produto_id)
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        names = request.json.get("tags", []) or []
        # pega só as que já existem
        existentes = db.query(Tag).filter(Tag.nome_tag.in_(names)).all()
        if not existentes:
            return jsonify({"status": "error", "message": "Nenhuma das tags existe."}), 400

        # atribui (sem duplicar)
        for t in existentes:
            if t not in produto.tags:
                produto.tags.append(t)
        db.commit()

        # reprocessa para verificar elegibilidade de oferta
        return _api_reprocess_single_product(produto_id)

    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# helper reaproveitável
def _api_reprocess_single_product(produto_id: int):
    from backend.modules.collector import Collector
    db2 = SessionLocal()
    try:
        produto2 = db2.get(Produto, produto_id)
        if not produto2:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        col = Collector(db2)

        # tenta resolver a loja via MLB do link ou fallback (método que você já tem)
        loja, _ = None, None
        # se você já tiver _resolve_store_by_alt_or_scrape no Collector, use:
        try:
            loja, _ = col._resolve_store_by_alt_or_scrape(produto2.url_base)  # usa sua lógica de MLB/seller
        except Exception:
            loja = None

        # re-scrape do produto para obter preço/descrição atualizados
        pdata = col._scrape_mercadolivre_product(produto2.url_base)
        # força os IDs do produto conhecidos (product_id_loja) dentro de pdata
        pdata['product_id_loja'] = produto2.product_id_loja
        pdata['url_base'] = produto2.url_base

        created = col._save_product_and_offer(pdata, loja)
        col.browser.close()

        msg = "Produto reprocessado; oferta criada." if created else "Produto reprocessado; sem oferta elegível."
        return jsonify({"status": "success", "message": msg}), 200

    except Exception as e:
        db2.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db2.close()

@api_bp.route("/produtos/<int:produto_id>/reprocessar", methods=["POST"])
def api_reprocess_product(produto_id):
    return _api_reprocess_single_product(produto_id)

@api_bp.route("/lojas/ativar_by_produto/<int:produto_id>", methods=["POST"])
def api_ativar_loja_por_produto(produto_id: int):
    """
    Ativa (ativa=True) a loja já cadastrada relacionada ao produto via seller_id (product_id_loja)
    ou id alternativo (product_id_loja_alt). NÃO cria nova loja. Se não encontrar, erro.
    """
    db = SessionLocal()
    try:
        produto = db.get(Produto, produto_id)
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        seller_id = (produto.product_id_loja or "").strip()
        alt_id = (produto.product_id_loja_alt or "").strip()

        if not seller_id and not alt_id:
            return jsonify({"status": "error", "message": "Produto não possui identificadores de loja."}), 422

        q = db.query(LojaConfiavel)
        from sqlalchemy import or_
        loja = q.filter(
            or_(
                LojaConfiavel.id_loja_api == seller_id if seller_id else False,
                LojaConfiavel.id_loja_api_alt == alt_id if alt_id else False
            )
        ).first()

        if not loja:
            return jsonify({"status": "error", "message": "Não há loja cadastrada para este produto."}), 404

        if not loja.ativa:
            loja.ativa = True
        # garante campo lojaconfiavel=True se existir
        if hasattr(loja, "lojaconfiavel") and loja.lojaconfiavel is False:
            loja.lojaconfiavel = True

        db.commit()
        return jsonify({
            "status": "success",
            "message": "Loja ativada com sucesso.",
            "loja": {
                "id": loja.id,
                "nome_loja": loja.nome_loja,
                "id_loja_api": loja.id_loja_api,
                "id_loja_api_alt": loja.id_loja_api_alt,
                "ativa": loja.ativa
            }
        }), 200
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()