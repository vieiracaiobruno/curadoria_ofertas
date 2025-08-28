
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db.database import Base, produto_tags_association, canal_tags_association

# Definição dos Modelos
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    is_admin = Column(Boolean, default=False)

class LojaConfiavel(Base):
    __tablename__ = "lojas_confiaveis"
    id = Column(Integer, primary_key=True, index=True)
    nome_loja = Column(String, unique=True, nullable=False)
    plataforma = Column(String, nullable=False)
    id_loja_api = Column(String, nullable=True)
    pontuacao_confianca = Column(Integer, default=3, nullable=False)
    ativa = Column(Boolean, default=True, nullable=False)

    historico_precos = relationship("HistoricoPreco", back_populates="loja")
    ofertas = relationship("Oferta", back_populates="loja")

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    nome_tag = Column(String, unique=True, nullable=False)

    produtos = relationship("Produto", secondary=produto_tags_association, back_populates="tags")
    canais = relationship("CanalTelegram", secondary=canal_tags_association, back_populates="tags")

class CanalTelegram(Base):
    __tablename__ = "canais_telegram"
    id = Column(Integer, primary_key=True, index=True)
    id_canal_api = Column(String, unique=True, nullable=False)
    nome_amigavel = Column(String, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    inscritos = Column(Integer, default=0, nullable=False)

    tags = relationship("Tag", secondary=canal_tags_association, back_populates="canais")
    ofertas_publicadas = relationship("OfertaPublicada", back_populates="canal")

class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    product_id_loja = Column(String, unique=True, nullable=False)
    nome_produto = Column(String, nullable=False)
    url_base = Column(String, nullable=False)
    imagem_url = Column(String, nullable=True)

    tags = relationship("Tag", secondary=produto_tags_association, back_populates="produtos")
    historico_precos = relationship("HistoricoPreco", back_populates="produto")
    ofertas = relationship("Oferta", back_populates="produto")

class HistoricoPreco(Base):
    __tablename__ = "historico_precos"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey('produtos.id'), nullable=False)
    loja_id = Column(Integer, ForeignKey('lojas_confiaveis.id'), nullable=False)
    preco = Column(Float, nullable=False)
    data_verificacao = Column(DateTime, default=datetime.now, nullable=False)

    produto = relationship("Produto", back_populates="historico_precos")
    loja = relationship("LojaConfiavel", back_populates="historico_precos")

class Oferta(Base):
    __tablename__ = "ofertas"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey('produtos.id'), nullable=False)
    loja_id = Column(Integer, ForeignKey('lojas_confiaveis.id'), nullable=False)
    preco_original = Column(Float, nullable=True)
    preco_oferta = Column(Float, nullable=False)
    url_afiliado_longa = Column(String, nullable=False)
    url_afiliado_curta = Column(String, nullable=True)
    data_encontrado = Column(DateTime, default=datetime.now, nullable=False)
    data_validade = Column(DateTime, nullable=True)
    status = Column(String, default="PENDENTE_APROVACAO", nullable=False) # PENDENTE_APROVACAO, APROVADO, REJEITADO, AGENDADO, PUBLICADO
    motivo_validacao = Column(String, nullable=True)
    data_publicacao = Column(DateTime, nullable=True)
    mensagem_id_telegram = Column(String, nullable=True)

    produto = relationship("Produto", back_populates="ofertas")
    loja = relationship("LojaConfiavel", back_populates="ofertas")
    metricas = relationship("MetricaOferta", back_populates="oferta")

class MetricaOferta(Base):
    __tablename__ = "metricas_ofertas"
    id = Column(Integer, primary_key=True, index=True)
    oferta_id = Column(Integer, ForeignKey('ofertas.id'), nullable=False)
    cliques = Column(Integer, default=0, nullable=False)
    vendas = Column(Integer, default=0, nullable=False)
    data_atualizacao = Column(DateTime, default=datetime.now, nullable=False)

    oferta = relationship("Oferta", back_populates="metricas")

class OfertaPublicada(Base):
    __tablename__ = "ofertas_publicadas"
    id = Column(Integer, primary_key=True, index=True)
    oferta_id = Column(Integer, ForeignKey('ofertas.id'), nullable=False)
    canal_id = Column(Integer, ForeignKey('canais_telegram.id'), nullable=False)
    data_publicacao = Column(DateTime, default=datetime.now, nullable=False)
    mensagem_id_telegram = Column(String, nullable=True)

    oferta = relationship("Oferta")
    canal = relationship("CanalTelegram", back_populates="ofertas_publicadas")


