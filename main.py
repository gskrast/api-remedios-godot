from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- CONFIGURAÇÃO DE CORS (ESSENCIAL PARA GODOT WEB) ---
# Isso permite que seu jogo na Web acesse essa API sem ser bloqueado pelo navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, troque "*" pelo endereço do seu jogo (ex: itch.io)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELO DE DADOS ---
# Define como é o formato do Remédio
class HistoricoCompra(BaseModel):
    preco: float
    local: str

class Remedio(BaseModel):
    id: Optional[int] = None
    nome: str
    dose_diaria: int
    doses_caixa: int
    cpf_convenio: Optional[str] = ""
    historico_compras: List[HistoricoCompra] = []
    
    # Campo calculado (não precisamos enviar, a API calcula)
    dias_restantes: Optional[int] = 0

# --- BANCO DE DADOS SIMULADO ---
remedios_db = [
    {
        "id": 1,
        "nome": "Dipirona",
        "dose_diaria": 3,
        "doses_caixa": 30,
        "dias_restantes": 10,
        "cpf_convenio": "123.456.789-00",
        "historico_compras": [
            {"preco": 15.50, "local": "Farmacia A"},
            {"preco": 16.00, "local": "Farmacia B"}
        ]
    }
]

# --- ROTAS DA API ---

@app.get("/")
def home():
    return {"mensagem": "API de Remédios Online!"}

@app.get("/remedios")
def listar_remedios():
    return remedios_db

@app.post("/remedios")
def criar_remedio(remedio: Remedio):
    # Gera um novo ID
    novo_id = 1
    if len(remedios_db) > 0:
        novo_id = remedios_db[-1]["id"] + 1
    
    remedio.id = novo_id
    
    # Lógica simples para calcular dias restantes
    if remedio.dose_diaria > 0:
        remedio.dias_restantes = int(remedio.doses_caixa / remedio.dose_diaria)
    else:
        remedio.dias_restantes = 0
        
    # Converte para dicionário e salva
    remedios_db.append(remedio.dict())
    return remedio

@app.put("/remedios/{remedio_id}")
def atualizar_remedio(remedio_id: int, remedio_atualizado: Remedio):
    for index, item in enumerate(remedios_db):
        if item["id"] == remedio_id:
            # Mantém o ID original
            remedio_atualizado.id = remedio_id
            
            # Recalcula dias
            if remedio_atualizado.dose_diaria > 0:
                remedio_atualizado.dias_restantes = int(remedio_atualizado.doses_caixa / remedio_atualizado.dose_diaria)
            
            # Atualiza na lista
            remedios_db[index] = remedio_atualizado.dict()
            return remedio_atualizado
            
    raise HTTPException(status_code=404, detail="Remédio não encontrado")