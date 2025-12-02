from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime # <--- IMPORTANTE

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    data_inicio: Optional[str] = None
    dias_restantes: Optional[int] = 0
    # NOVO CAMPO
    na_lista_compras: Optional[bool] = False

remedios_db = []

@app.get("/remedios")
def listar_remedios():
    hoje = date.today()
    
    for item in remedios_db:
        # Se tivermos a data de início e a dose for maior que 0, calculamos
        if item["data_inicio"] and item["dose_diaria"] > 0:
            # 1. Converte a string "2023-XX-XX" de volta para Objeto Data
            data_inicio = date.fromisoformat(item["data_inicio"])
            
            # 2. Quantos dias o remédio dura no total? (Ex: 30 comp / 3 por dia = 10 dias)
            duracao_total = int(item["doses_caixa"] / item["dose_diaria"])
            
            # 3. Quantos dias já se passaram desde que adicionou?
            dias_passados = (hoje - data_inicio).days
            
            # 4. Cálculo final
            dias_restantes = duracao_total - dias_passados
            item["dias_restantes"] = dias_restantes
        else:
            item["dias_restantes"] = 0
            
    return remedios_db

@app.post("/remedios")
def criar_remedio(remedio: Remedio):
    novo_id = 1
    if len(remedios_db) > 0:
        novo_id = remedios_db[-1]["id"] + 1
    remedio.id = novo_id
    remedio.data_inicio = str(date.today())
    
    # Se for criado já com 0 dias ou estoque baixo, já sugere ir pra lista
    if remedio.dose_diaria > 0:
        remedio.dias_restantes = int(remedio.doses_caixa / remedio.dose_diaria)
    
    remedios_db.append(remedio.dict())
    return remedio

@app.put("/remedios/{remedio_id}")
def atualizar_remedio(remedio_id: int, remedio_atualizado: Remedio):
    for index, item in enumerate(remedios_db):
        if item["id"] == remedio_id:
            remedio_atualizado.id = remedio_id
            
            # Mantém a data de início original (para não resetar a contagem)
            # A menos que você queira que editar RESETE o tempo, aí remova essa linha
            remedio_atualizado.data_inicio = item["data_inicio"]
            
            remedios_db[index] = remedio_atualizado.dict()
            return remedio_atualizado
            
    raise HTTPException(status_code=404, detail="Remédio não encontrado")