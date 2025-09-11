import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime
from dotenv import load_dotenv

# Carrega .env
load_dotenv('config.env')

# DB e Models (use SEMPRE os objetos do database.py)
from backend.db.database import SessionLocal, engine, create_db_tables
#from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto
from backend.utils.auth import hash_password, check_password
from sqlalchemy.orm import joinedload, selectinload
import unicodedata, re

from backend.utils.config import get_config

# Garantir as tabelas uma ÚNICA vez, usando o bootstrap centralizado do database.py
create_db_tables()

app = Flask(__name__, template_folder='./frontend/templates', static_folder='./frontend/static')
#app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "sua_chave_secreta_aqui_para_producao")
app.config["SECRET_KEY"] = get_config("SECRET_KEY", "sua_chave_secreta_aqui_para_producao")  # :contentReference[oaicite:10]{index=10}

# Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Classe compatível com Flask-Login
class UserLogin(UserMixin):
    def __init__(self, user: Usuario):
        self.id = user.id
        self.username = user.username
        self.email = user.email
        self.is_admin = user.is_admin

@login_manager.user_loader
def load_user(user_id):
    try:
        uid = int(user_id)
    except ValueError:
        return None
    # Fecha a sessão automaticamente ao fim do bloco
    with SessionLocal() as db:
        user = db.get(Usuario, uid)  # SQLAlchemy 2.x
        return UserLogin(user) if user else None

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with SessionLocal() as db:
            user = db.query(Usuario).filter_by(username=username).first()

        if user and check_password(password, user.password_hash):
            login_user(UserLogin(user))
            flash("Login bem-sucedido!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Nome de usuário ou senha inválidos.", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Você foi desconectado.", "info")
    return redirect(url_for("login"))

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)

def _compile_pat(token: str):
    if len(token) <= 3 and re.fullmatch(r"[a-z0-9]+", token or ""):
        return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.I)
    return re.compile(re.escape(token), re.I)

@app.route("/")
@app.route("/dashboard")
@login_required
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
@login_required
def publicadas():
    with SessionLocal() as db:
        ofertas_publicadas = db.query(Oferta).filter(Oferta.status == "PUBLICADO").all()
        tags = db.query(Tag).all()
    return render_template("ofertas_publicadas.html", ofertas=ofertas_publicadas, tags=tags)

@app.route("/configuracoes")
@login_required
def configuracoes():
    with SessionLocal() as db:
        lojas = db.query(LojaConfiavel).all()
        tags = db.query(Tag).all()
        canais = (db.query(CanalTelegram)
                    .options(joinedload(CanalTelegram.tags))
                    .all())
    return render_template("configuracoes.html", lojas=lojas, tags=tags, canais=canais)

# Registrar blueprint da API
from backend.routes.api import api_bp
app.register_blueprint(api_bp, url_prefix="/api")

# Rota para adicionar um usuário admin inicial (apenas para setup)
@app.route("/setup_admin")
def setup_admin():
    admin_username = get_config("ADMIN_USERNAME", "admin")        # :contentReference[oaicite:11]{index=11}
    admin_email    = get_config("ADMIN_EMAIL", "admin@example.com")
    admin_password = get_config("ADMIN_PASSWORD", "admin_password")

    with SessionLocal() as db:
        if not db.query(Usuario).filter_by(username=admin_username).first():
            hashed_pw = hash_password(admin_password)
            admin_user = Usuario(
                username=admin_username,
                password_hash=hashed_pw,
                email=admin_email,
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            return "Usuário admin criado com sucesso!", 200
    return "Usuário admin já existe.", 200

@app.route("/produtos")
@login_required
def lista_produtos():
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
    return render_template("produtos.html", produtos=produtos)

@app.route("/variaveis")
@login_required
def variaveis():
    return render_template("env_vars.html")

if __name__ == "__main__":
    # Garante tabelas e cria admin se necessário
    create_db_tables()

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin_password")

    with SessionLocal() as db:
        if not db.query(Usuario).filter_by(username=admin_username).first():
            hashed_pw = hash_password(admin_password)
            admin_user = Usuario(
                username=admin_username,
                password_hash=hashed_pw,
                email=admin_email,
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            print(f"Usuário admin inicial '{admin_username}' criado.")

    #app.run(
    #    #debug=os.getenv("FLASK_DEBUG", "True").lower() == "true",
    #    host="0.0.0.0",
    #    port=5000
    #)
    debug_flag = (get_config("FLASK_DEBUG", "True") or "True").lower() == "true"
    app.run(debug=debug_flag, host="0.0.0.0", port=5000)
