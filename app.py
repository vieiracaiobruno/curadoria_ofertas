
import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import bcrypt
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

from backend.db.database import DATABASE_URL, Base, SessionLocal
from backend.models.models import Usuario, Oferta, LojaConfiavel, Tag, CanalTelegram, Produto, MetricaOferta
from backend.utils.auth import hash_password, check_password

app = Flask(__name__, template_folder='./frontend/templates', static_folder='./frontend/static')
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "sua_chave_secreta_aqui_para_producao")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Configuração do banco de dados
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine) # Garante que as tabelas existam

# Classe para compatibilidade com Flask-Login
class UserLogin(UserMixin):
    def __init__(self, user):
        self.id = user.id
        self.username = user.username
        self.email = user.email
        self.is_admin = user.is_admin

@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    user = db.query(Usuario).get(int(user_id))
    db.close()
    if user:
        return UserLogin(user)
    return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = SessionLocal()
        user = db.query(Usuario).filter_by(username=username).first()
        db.close()

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

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    db = SessionLocal()
    ofertas_pendentes = db.query(Oferta).filter(Oferta.status == "PENDENTE_APROVACAO").all()
    db.close()
    return render_template("fila_aprovacao.html", ofertas=ofertas_pendentes)

@app.route("/publicadas")
@login_required
def publicadas():
    db = SessionLocal()
    # Exemplo de consulta para ofertas publicadas com métricas
    # Em uma aplicação real, você faria paginação e filtros aqui
    ofertas_publicadas = db.query(Oferta).filter(Oferta.status == "PUBLICADO").all()
    tags = db.query(Tag).all()
    db.close()
    return render_template("ofertas_publicadas.html", ofertas=ofertas_publicadas, tags=tags)

@app.route("/configuracoes")
@login_required
def configuracoes():
    db = SessionLocal()
    lojas = db.query(LojaConfiavel).all()
    tags = db.query(Tag).all()
    canais = db.query(CanalTelegram).all()
    db.close()
    return render_template("configuracoes.html", lojas=lojas, tags=tags, canais=canais)

# Registrar blueprint da API
from backend.routes.api import api_bp
app.register_blueprint(api_bp, url_prefix="/api")

# Rota para adicionar um usuário admin inicial (apenas para setup)
@app.route("/setup_admin")
def setup_admin():
    db = SessionLocal()
    if not db.query(Usuario).filter_by(username=os.getenv("ADMIN_USERNAME", "admin")).first():
        hashed_pw = hash_password(os.getenv("ADMIN_PASSWORD", "admin_password"))
        admin_user = Usuario(
            username=os.getenv("ADMIN_USERNAME", "admin"), 
            password_hash=hashed_pw, 
            email=os.getenv("ADMIN_EMAIL", "admin@example.com"), 
            is_admin=True
        )
        db.add(admin_user)
        db.commit()
        db.close()
        return "Usuário admin criado com sucesso!", 200
    db.close()
    return "Usuário admin já existe.", 200

if __name__ == "__main__":
    # Crie um usuário admin inicial se não existir
    with app.app_context():
        db = SessionLocal()
        if not db.query(Usuario).filter_by(username=os.getenv("ADMIN_USERNAME", "admin")).first():
            hashed_pw = hash_password(os.getenv("ADMIN_PASSWORD", "admin_password"))
            admin_user = Usuario(
                username=os.getenv("ADMIN_USERNAME", "admin"), 
                password_hash=hashed_pw, 
                email=os.getenv("ADMIN_EMAIL", "admin@example.com"), 
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            print(f"Usuário admin inicial '{os.getenv('ADMIN_USERNAME', 'admin')}' criado.")
        db.close()

    app.run(
        debug=os.getenv("FLASK_DEBUG", "True").lower() == "true", 
        host="0.0.0.0", 
        port=5000
    )
