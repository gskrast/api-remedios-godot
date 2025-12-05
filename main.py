import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS ---

# Tenta pegar a URL do Render. Se não achar, cria um arquivo local "remedios.db"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./remedios.db")

# Correção necessária para o Render (ele usa postgres:// mas o SQLAlchemy quer postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. MODELOS DO BANCO (TABELAS) ---

class RemedioDB(Base):
    __tablename__ = "remedios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, index=True)
    dose_diaria = Column(Integer)
    doses_caixa = Column(Integer)
    cpf_convenio = Column(String, nullable=True)
    data_inicio = Column(String) # Vamos salvar como texto "YYYY-MM-DD" para simplificar
    na_lista_compras = Column(Boolean, default=False)
    
    # Relacionamento: Um remédio tem vários históricos
    historico_compras = relationship("HistoricoDB", back_populates="remedio", cascade="all, delete-orphan")

class HistoricoDB(Base):
    __tablename__ = "historico_compras"

    id = Column(Integer, primary_key=True, index=True)
    remedio_id = Column(Integer, ForeignKey("remedios.id"))
    preco = Column(Float)
    local = Column(String)
    
    remedio = relationship("RemedioDB", back_populates="historico_compras")

# Cria as tabelas automaticamente se não existirem
Base.metadata.create_all(bind=engine)

# --- 3. SCHEMAS PYDANTIC (COMUNICAÇÃO API) ---

class HistoricoCompra(BaseModel):
    preco: float
    local: str
    
    class Config:
        from_attributes = True # Permite ler do Banco de Dados

class RemedioCreate(BaseModel):
    nome: str
    dose_diaria: int
    doses_caixa: int
    cpf_convenio: Optional[str] = ""
    historico_compras: List[HistoricoCompra] = []
    # IMPORTANTE: Adicionado para receber o status do Godot
    na_lista_compras: Optional[bool] = False 

class RemedioResponse(BaseModel):
    id: int
    nome: str
    dose_diaria: int
    doses_caixa: int
    cpf_convenio: Optional[str] = ""
    historico_compras: List[HistoricoCompra] = []
    data_inicio: Optional[str] = None
    dias_restantes: Optional[int] = 0
    na_lista_compras: bool

    class Config:
        from_attributes = True

# --- 4. APP FASTAPI ---

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependência para abrir/fechar conexão com o banco a cada requisição
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 5. LÓGICA DE CÁLCULO ---
def calcular_dias_restantes(remedio_db):
    if not remedio_db.data_inicio or remedio_db.dose_diaria <= 0:
        return 0
        
    try:
        hoje = date.today()
        # Converte string do banco para data real
        data_inicio = date.fromisoformat(remedio_db.data_inicio)
        
        # Lógica: (Total da Caixa / Dose Diária) - Dias Passados
        duracao_total = int(remedio_db.doses_caixa / remedio_db.dose_diaria)
        dias_passados = (hoje - data_inicio).days
        
        restantes = duracao_total - dias_passados
        return restantes
    except:
        return 0

# --- 6. ROTAS ---

@app.get("/remedios", response_model=List[RemedioResponse])
def listar_remedios(db: Session = Depends(get_db)):
    # Busca tudo do banco
    remedios = db.query(RemedioDB).all()
    
    # Processa cada um para inserir o cálculo dinâmico de dias
    for item in remedios:
        item.dias_restantes = calcular_dias_restantes(item)
        
    return remedios

@app.post("/remedios", response_model=RemedioResponse)
def criar_remedio(remedio: RemedioCreate, db: Session = Depends(get_db)):
    # 1. Prepara o objeto principal
    db_remedio = RemedioDB(
        nome=remedio.nome,
        dose_diaria=remedio.dose_diaria,
        doses_caixa=remedio.doses_caixa,
        cpf_convenio=remedio.cpf_convenio,
        data_inicio=str(date.today()), # Salva data de hoje como string
        na_lista_compras=remedio.na_lista_compras
    )
    
    # 2. Salva o remédio
    db.add(db_remedio)
    db.commit()
    db.refresh(db_remedio) # Atualiza para pegar o ID gerado
    
    # 3. Salva o histórico (se houver)
    for hist in remedio.historico_compras:
        db_hist = HistoricoDB(
            remedio_id=db_remedio.id,
            preco=hist.preco,
            local=hist.local
        )
        db.add(db_hist)
    
    db.commit()
    db.refresh(db_remedio)
    
    # Calcula dias para o retorno
    db_remedio.dias_restantes = calcular_dias_restantes(db_remedio)
    
    return db_remedio

@app.put("/remedios/{remedio_id}", response_model=RemedioResponse)
def atualizar_remedio(remedio_id: int, remedio_atualizado: RemedioCreate, db: Session = Depends(get_db)):
    # Busca o remédio existente
    db_remedio = db.query(RemedioDB).filter(RemedioDB.id == remedio_id).first()
    
    if not db_remedio:
        raise HTTPException(status_code=404, detail="Remédio não encontrado")
    
    # Atualiza campos básicos
    db_remedio.nome = remedio_atualizado.nome
    db_remedio.dose_diaria = remedio_atualizado.dose_diaria
    db_remedio.doses_caixa = remedio_atualizado.doses_caixa
    db_remedio.cpf_convenio = remedio_atualizado.cpf_convenio
    
    # Atualiza o status da lista de compras!
    db_remedio.na_lista_compras = remedio_atualizado.na_lista_compras
    
    # Atualiza histórico (Estratégia: Remove antigos e recria novos)
    # Isso evita ter que gerenciar IDs de histórico individualmente no frontend
    db.query(HistoricoDB).filter(HistoricoDB.remedio_id == remedio_id).delete()
    
    for hist in remedio_atualizado.historico_compras:
        db_hist = HistoricoDB(
            remedio_id=remedio_id,
            preco=hist.preco,
            local=hist.local
        )
        db.add(db_hist)
        
    db.commit()
    db.refresh(db_remedio)
    
    db_remedio.dias_restantes = calcular_dias_restantes(db_remedio)
    return db_remedio

@app.delete("/remedios/{remedio_id}")
def deletar_remedio(remedio_id: int, db: Session = Depends(get_db)):
    db_remedio = db.query(RemedioDB).filter(RemedioDB.id == remedio_id).first()
    
    if not db_remedio:
        raise HTTPException(status_code=404, detail="Remédio não encontrado")
        
    db.delete(db_remedio)
    db.commit()
    return {"mensagem": "Remédio removido com sucesso"}