"""Operações administrativas restritas à operadora da sessão."""
import re
import secrets
import sqlite3

from backend import storage


def pagina(query):
    valor = query.get("pagina",["1"])[0]
    if not re.fullmatch(r"[1-9][0-9]{0,5}",valor):
        raise ValueError("Página inválida.")
    return int(valor)


def salvar_auditor(conn,s,d):
    tenant,actor = s["tenant"],s["user"]
    nome = d.get("username","").strip()
    acao = d.get("acao")
    existente = conn.execute("SELECT role FROM users WHERE tenant_id=? AND username=?",(tenant,nome)).fetchone()
    if acao != "criar" and (not existente or existente["role"]!="auditor"):
        raise ValueError("Auditor indisponível.")
    if acao in ("inativar","reativar"):
        if acao=="inativar":
            conn.execute("INSERT OR IGNORE INTO auditor_disabled VALUES(?)",(nome,))
        else:
            conn.execute("DELETE FROM auditor_disabled WHERE username=?",(nome,))
        conn.execute("UPDATE auditor_profiles SET modified=? WHERE tenant=? AND username=?",(storage.now(),tenant,nome))
    elif acao in ("criar","editar"):
        completo,crm,uf,email = (d.get(k,"").strip() for k in ("name","crm","uf","email"))
        uf = uf.upper()
        if (not re.fullmatch(r"[a-zA-Z0-9_.-]{3,60}",nome) or not 2<=len(completo)<=120
            or not re.fullmatch(r"[1-9][0-9]{0,7}",crm) or uf not in
            "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
            or len(email)>254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+",email)):
            raise ValueError("Confira usuário, nome, CRM, UF e e-mail.")
        try:
            with conn:
                if acao=="criar":
                    senha = secrets.token_urlsafe(18)
                    salt = secrets.token_bytes(16)
                    conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",(nome,tenant,"auditor",salt,storage.digest(senha,salt),storage.now()))
                conn.execute("""INSERT INTO auditor_profiles(username,tenant,name,crm,uf,email,modified)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET name=excluded.name,
                    crm=excluded.crm,uf=excluded.uf,email=excluded.email,modified=excluded.modified""",
                    (nome,tenant,completo,crm,uf,email,storage.now()))
                storage.audit(conn,tenant,actor,acao+"_auditor","user",nome)
        except sqlite3.IntegrityError:
            raise ValueError("Usuário, CRM/UF ou e-mail já cadastrado.") from None
        return (nome,senha) if acao=="criar" else None
    else:
        raise ValueError("Ação inválida.")
    storage.audit(conn,tenant,actor,acao+"_auditor","user",nome)
