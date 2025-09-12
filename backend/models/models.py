from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

# Importa SEMPRE a mesma Base
try:
    from ..db.database import Base
except Exception:
    from database import Base

# Tabelas de ligação N:N
produto_tags = Table(
    'produto_tags',
    Base.metadata,
    Column('produto_id', Integer, ForeignKey('produtos.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True),
)

canal_tags = Table(
    'canal_tags',
    Base.metadata,
    Column('canal_id', Integer, ForeignKey('canais_telegram.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True),
)

# --------- Modelos ---------
class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    is_admin = Column(Boolean, default=False)

class LojaConfiavel(Base):
    __tablename__ = "lojas_confiaveis"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    nome_loja = Column(String, unique=True, nullable=False)
    plataforma = Column(String, nullable=False)
    id_loja_api = Column(String, nullable=True)  # seller_id
    id_loja_api_alt = Column(String, unique=True, nullable=True)
    pontuacao_confianca = Column(Integer, default=3, nullable=False)
    ativa = Column(Boolean, default=True, nullable=False)
    historico_precos = relationship("HistoricoPreco", back_populates="loja")
    ofertas = relationship("Oferta", back_populates="loja")

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    nome_tag = Column(String, unique=True, nullable=False)

    produtos = relationship("Produto", secondary="produto_tags", back_populates="tags")
    canais = relationship("CanalTelegram", secondary="canal_tags", back_populates="tags")

class CanalTelegram(Base):
    __tablename__ = "canais_telegram"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    id_canal_api = Column(String, unique=True, nullable=False)
    nome_amigavel = Column(String, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    inscritos = Column(Integer, default=0, nullable=False)

    tags = relationship("Tag", secondary="canal_tags", back_populates="canais")
    ofertas_publicadas = relationship("OfertaPublicada", back_populates="canal")

class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    id_product = Column(String, unique=True, nullable=False)
    product_id_loja = Column(String, nullable=False, index=True)
    product_id_loja_alt = Column(String, nullable=True, index=True)
    nome_produto = Column(String, nullable=False)
    url_base = Column(String, nullable=False)
    imagem_url = Column(String, nullable=True)
    tags = relationship("Tag", secondary="produto_tags", back_populates="produtos")
    historico_precos = relationship("HistoricoPreco", back_populates="produto")
    ofertas = relationship("Oferta", back_populates="produto")

class HistoricoPreco(Base):
    __tablename__ = "historico_precos"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey('produtos.id'), nullable=False)
    loja_id = Column(Integer, ForeignKey('lojas_confiaveis.id'), nullable=False)
    preco = Column(Float, nullable=False)
    data_verificacao = Column(DateTime, default=datetime.now, nullable=False)

    produto = relationship("Produto", back_populates="historico_precos")
    loja = relationship("LojaConfiavel", back_populates="historico_precos")

class Oferta(Base):
    __tablename__ = "ofertas"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey('produtos.id'), nullable=False)
    loja_id = Column(Integer, ForeignKey('lojas_confiaveis.id'), nullable=False)
    preco_original = Column(Float, nullable=True)
    preco_oferta = Column(Float, nullable=False)
    url_afiliado_longa = Column(String, nullable=False)
    url_afiliado_curta = Column(String, nullable=True)
    data_encontrado = Column(DateTime, default=datetime.now, nullable=False)
    data_validade = Column(DateTime, nullable=True)
    status = Column(String, default="PENDENTE_APROVACAO", nullable=False)
    motivo_validacao = Column(String, nullable=True)
    data_publicacao = Column(DateTime, nullable=True)
    mensagem_id_telegram = Column(String, nullable=True)
    desconto_real = Column(Float, nullable=True)

    produto = relationship("Produto", back_populates="ofertas")
    loja = relationship("LojaConfiavel", back_populates="ofertas")
    metricas = relationship("MetricaOferta", back_populates="oferta")

class MetricaOferta(Base):
    __tablename__ = "metricas_ofertas"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    oferta_id = Column(Integer, ForeignKey('ofertas.id'), nullable=False)
    cliques = Column(Integer, default=0, nullable=False)
    vendas = Column(Integer, default=0, nullable=False)
    data_atualizacao = Column(DateTime, default=datetime.now, nullable=False)

    oferta = relationship("Oferta", back_populates="metricas")

class OfertaPublicada(Base):
    __tablename__ = "ofertas_publicadas"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    oferta_id = Column(Integer, ForeignKey('ofertas.id'), nullable=False)
    canal_id = Column(Integer, ForeignKey('canais_telegram.id'), nullable=False)
    data_publicacao = Column(DateTime, default=datetime.now, nullable=False)
    mensagem_id_telegram = Column(String, nullable=True)

    oferta = relationship("Oferta")
    canal = relationship("CanalTelegram", back_populates="ofertas_publicadas")

class ConfigVar(Base):
    __tablename__ = "config_vars"
    __table_args__ = {'extend_existing': True}
    __table_args__ = (
        UniqueConstraint("key", name="uq_config_vars_key"),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False)           # ex: "TELEGRAM_BOT_TOKEN"
    value = Column(String, nullable=True)          # valor em texto (encriptação opcional depois)
    is_secret = Column(Boolean, default=True, nullable=False)
    description = Column(String, nullable=True)    # dica/ajuda na UI
    updated_at = Column(DateTime, default=datetime.now, nullable=False)
