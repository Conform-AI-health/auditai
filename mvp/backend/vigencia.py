"""Catálogo local para ensaios de vigência. Datas e alterações exclusivamente fictícias."""
from pathlib import Path

BASE = "2026-11-21"
NOVA = "2026-12-01"
ROTULO = "Simulação de vigência · DUT 60"
ANTERIOR = "nódulo maior que um centímetro"
POSTERIOR = "nódulo de pelo menos um centímetro"

def preparar(conn, tenant):
    conn.execute("""CREATE TABLE IF NOT EXISTS dut_ensaio(
        tenant TEXT NOT NULL REFERENCES tenants(id), inicio TEXT NOT NULL,
        texto TEXT NOT NULL, aprovado_por TEXT, PRIMARY KEY(tenant,inicio))""")
    if not conn.execute("SELECT 1 FROM dut_ensaio WHERE tenant=? AND inicio=?", (tenant,BASE)).fetchone():
        texto = Path(__file__).with_name("DUT60.txt").read_text(encoding="utf-8")
        conn.execute("INSERT OR IGNORE INTO dut_ensaio VALUES(?,?,?,?)",(tenant,BASE,texto,"base de ensaio"))

def propor(conn, tenant):
    preparar(conn, tenant)
    texto = conn.execute("SELECT texto FROM dut_ensaio WHERE tenant=? AND inicio=?", (tenant,BASE)).fetchone()[0]
    if texto.count(ANTERIOR) != 1:
        raise ValueError("O texto de origem mudou. Confira o subitem antes do ensaio.")
    return conn.execute("INSERT OR IGNORE INTO dut_ensaio VALUES(?,?,?,NULL)",
                        (tenant,NOVA,texto.replace(ANTERIOR,POSTERIOR))).rowcount

def selecionar(conn,tenant,data_caso):
    preparar(conn,tenant)
    row=conn.execute("""SELECT inicio,texto,aprovado_por FROM dut_ensaio
        WHERE tenant=? AND inicio<=? ORDER BY inicio DESC LIMIT 1""",(tenant,data_caso)).fetchone()
    if not row or not row["aprovado_por"]:
        raise ValueError("A data do caso exige uma versão aprovada. Encaminhe para revisão.")
    return dict(row)
