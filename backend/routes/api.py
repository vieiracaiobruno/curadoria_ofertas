from flask import Blueprint, request, jsonify
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime

from ..db.database import DATABASE_URL, Base, SessionLocal
from ..models.models import Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta

api_bp = Blueprint("api", __name__)

# Helper para obter a sessão do DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@api_bp.route("/canais_destino", methods=["GET"])
def get_canais_destino():
    tags_str = request.args.get("tags", "")
    tags_list = [t.strip() for t in tags_str.split(",") if t.strip()]

    db = SessionLocal()
    canais_encontrados = []
    if tags_list:
        # Busca as tags no banco de dados
        tags_obj = db.query(Tag).filter(Tag.nome_tag.in_(tags_list)).all()
        tag_ids = [tag.id for tag in tags_obj]

        if tag_ids:
            # Busca canais que possuem ALGUMA das tags
            canais_encontrados = db.query(CanalTelegram).join(CanalTelegram.tags).filter(
                CanalTelegram.ativo == True,
                Tag.id.in_(tag_ids)
            ).distinct().all()
    
    db.close()

    canais_data = [{
        "id": canal.id,
        "nome_amigavel": canal.nome_amigavel,
        "id_canal_api": canal.id_canal_api
    } for canal in canais_encontrados]

    return jsonify({"status": "success", "canais": canais_data}), 200

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
        if produto is not None and tags_from_frontend is not None: # Permite [] para remover todas
            # Remove tags existentes
            produto.tags.clear()
            # Adiciona novas tags
            for tag_name in tags_from_frontend:
                tag = db.query(Tag).filter_by(nome_tag=tag_name.replace("#", "")).first()
                if not tag:
                    tag = Tag(nome_tag=tag_name.replace("#", ""))
                    db.add(tag)
                    db.flush() # Garante que a tag tenha um ID antes de ser associada
                produto.tags.append(tag)

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

# Rotas para gerenciar Lojas Confiáveis
@api_bp.route("/lojas", methods=["POST"])
def api_add_loja():
    db = SessionLocal()
    data = request.json
    try:
        loja = LojaConfiavel(
            nome_loja=data["nome_loja"],
            plataforma=data["plataforma"],
            id_loja_api=data.get("id_loja_api"),
            pontuacao_confianca=data.get("pontuacao_confianca", 3),
            ativa=data.get("ativa", True)
        )
        db.add(loja)
        db.commit()
        return jsonify({"status": "success", "message": "Loja adicionada com sucesso!"}), 201
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

# Rotas para gerenciar Tags
@api_bp.route("/tags", methods=["POST"])
def api_add_tag():
    db = SessionLocal()
    data = request.json
    try:
        tag_name = data["nome_tag"].lower()
        existing_tag = db.query(Tag).filter_by(nome_tag=tag_name).first()
        if existing_tag:
            return jsonify({"status": "error", "message": "Tag já existe."}), 409

        tag = Tag(nome_tag=tag_name)
        db.add(tag)
        db.commit()
        return jsonify({"status": "success", "message": "Tag adicionada com sucesso!"}), 201
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

# Rotas para gerenciar Canais Telegram
@api_bp.route("/canais", methods=["POST"])
def api_add_canal():
    db = SessionLocal()
    data = request.json
    try:
        canal = CanalTelegram(
            nome_amigavel=data["nome_amigavel"],
            id_canal_api=data["id_canal_api"],
            inscritos=data.get("inscritos", 0),
            ativo=data.get("ativo", True)
        )
        db.add(canal)
        db.flush() # Para obter o ID do canal antes de associar tags

        tags_associadas = data.get("tags_associadas", [])
        for tag_name in tags_associadas:
            tag = db.query(Tag).filter_by(nome_tag=tag_name.lower()).first()
            if not tag:
                tag = Tag(nome_tag=tag_name.lower())
                db.add(tag)
                db.flush()
            canal.tags.append(tag)

        db.commit()
        return jsonify({"status": "success", "message": "Canal adicionado com sucesso!"}), 201
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
        canal.nome_amigavel = data.get("nome_amigavel", canal.nome_amigavel)
        canal.id_canal_api = data.get("id_canal_api", canal.id_canal_api)
        canal.inscritos = data.get("inscritos", canal.inscritos)
        canal.ativo = data.get("ativo", canal.ativo)

        # Atualiza tags associadas
        tags_associadas = data.get("tags_associadas")
        if tags_associadas is not None: # Permite que seja [] para remover todas
            canal.tags.clear()
            for tag_name in tags_associadas:
                tag = db.query(Tag).filter_by(nome_tag=tag_name.lower()).first()
                if not tag:
                    tag = Tag(nome_tag=tag_name.lower())
                    db.add(tag)
                    db.flush()
                canal.tags.append(tag)

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
