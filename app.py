import datetime
import calendar
import base64
import io
import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from supabase import Client, create_client

# 1. Configuração da Página do Streamlit
st.set_page_config(
    page_title="R² Bonés - Controle Gerencial Pro",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Personalizada
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    }

    .custom-header-container {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        padding: 22px 30px;
        border-radius: 16px;
        color: white;
        display: flex;
        align-items: center;
        gap: 25px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.12);
        margin-bottom: 25px;
        width: 100%;
    }

    .header-text h1 {
        margin: 0;
        font-size: 2.1em;
        font-weight: 700;
        color: #ffffff;
    }

    .header-text p {
        margin: 4px 0 0 0;
        opacity: 0.85;
        font-size: 1.05em;
    }

    div[data-testid="stImage"] > img {
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.08);
        margin-bottom: 10px;
        width: 100% !important;
        max-height: 160px !important;
        object-fit: contain !important;
    }

    .kpi-card-advanced {
        background: #ffffff;
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        border-top: 4px solid #3b82f6;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        position: relative;
    }

    .kpi-card-advanced:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 30px rgba(0,0,0,0.12);
    }

    .kpi-title {
        font-size: 0.85em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748b;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .kpi-value {
        font-size: 1.8em;
        font-weight: 800;
        color: #0f172a;
    }

    .tooltip-icon {
        display: inline-block;
        background: #e2e8f0;
        color: #475569;
        border-radius: 50%;
        width: 18px;
        height: 18px;
        text-align: center;
        font-size: 11px;
        line-height: 18px;
        cursor: pointer;
        margin-left: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Cache em sessão para guardar custos avulsos, baixas e devoluções locais
if "extra_costs_cache" not in st.session_state:
    st.session_state["extra_costs_cache"] = {}

if "custos_avulsos_local" not in st.session_state:
    st.session_state["custos_avulsos_local"] = []

if "baixas_estoque_local" not in st.session_state:
    st.session_state["baixas_estoque_local"] = []

if "devolucoes_venda_local" not in st.session_state:
    st.session_state["devolucoes_venda_local"] = []

# Configurações do Banco de Dados SQLite / Supabase
DB_NAME = "ordens_producao.db"
UPLOADS_DIR = "uploads"
COMPROVANTES_DIR = "comprovantes"

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

if not os.path.exists(COMPROVANTES_DIR):
    os.makedirs(COMPROVANTES_DIR)

# 2. Inicialização do Cliente Supabase
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

def carregar_dataframe(query, params=None):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id TEXT,
            data_criacao TEXT,
            cor_bone TEXT,
            frase_arte TEXT,
            cor_linha TEXT,
            tipo TEXT,
            preco REAL,
            observacoes TEXT,
            imagem_path TEXT,
            status TEXT,
            valor_estampa_extra REAL DEFAULT 0.0,
            valor_matriz REAL DEFAULT 0.0,
            codigo_produto TEXT,
            total_item REAL
        )
    ''')
    c.execute("PRAGMA table_info(pedidos)")
    colunas_pedidos = [column[1] for column in c.fetchall()]
    if "valor_estampa_extra" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN valor_estampa_extra REAL DEFAULT 0.0")
    if "valor_matriz" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN valor_matriz REAL DEFAULT 0.0")
    if "codigo_produto" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN codigo_produto TEXT")
    if "total_item" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN total_item REAL")

    c.execute("UPDATE pedidos SET tipo = 'Básico' WHERE tipo = 'Simples'")
    c.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_bone TEXT,
            codigo TEXT,
            cliente TEXT,
            qtd INTEGER DEFAULT 1,
            valor_venda REAL DEFAULT 0.0,
            tarifa REAL DEFAULT 0.0,
            tarifa_bancaria REAL DEFAULT 0.0,
            tarifa_cartao REAL DEFAULT 0.0,
            valor_recebido REAL DEFAULT 0.0,
            forma_pagto TEXT,
            data TEXT,
            data_venda TEXT,
            data_recebimento TEXT,
            custo REAL DEFAULT 0.0,
            custo_unitario REAL DEFAULT 0.0
        )
    ''')
    c.execute("PRAGMA table_info(vendas)")
    colunas_vendas = [column[1] for column in c.fetchall()]
    colunas_vendas_necessarias = {
        "codigo_bone": "TEXT", "codigo": "TEXT", "cliente": "TEXT",
        "qtd": "INTEGER DEFAULT 1", "valor_venda": "REAL DEFAULT 0.0",
        "tarifa": "REAL DEFAULT 0.0", "tarifa_bancaria": "REAL DEFAULT 0.0",
        "tarifa_cartao": "REAL DEFAULT 0.0", "valor_recebido": "REAL DEFAULT 0.0",
        "forma_pagto": "TEXT", "data": "TEXT", "data_venda": "TEXT",
        "data_recebimento": "TEXT", "custo": "REAL DEFAULT 0.0",
        "custo_unitario": "REAL DEFAULT 0.0"
    }
    for _col, _tipo in colunas_vendas_necessarias.items():
        if _col not in colunas_vendas:
            c.execute(f"ALTER TABLE vendas ADD COLUMN {_col} {_tipo}")

    c.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id TEXT,
            data_pagamento TEXT,
            valor_pago REAL,
            forma_pagamento TEXT,
            observacoes TEXT,
            comprovante_path TEXT
        )
    ''')
    c.execute("UPDATE pedidos SET status = 'Em Produção' WHERE status = 'Pendente'")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor_b64 TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS baixas_estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            motivo TEXT,
            observacao TEXT,
            data_baixa TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS devolucoes_vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER,
            codigo TEXT,
            cliente TEXT,
            valor_devolvido REAL,
            data_devolucao TEXT,
            motivo TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------
# FUNÇÕES ROBUSTAS DE TRATAMENTO E FORMATO DE DATAS (YYYY/MM/DD)
# ----------------------------------------------------
def parse_date_str(val):
    hoje = datetime.date.today().strftime("%Y/%m/%d")
    if val is None:
        return hoje
    try:
        if pd.isna(val):
            return hoje
    except Exception:
        pass
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y/%m/%d")
    if isinstance(val, datetime.datetime):
        return val.strftime("%Y/%m/%d")
    if isinstance(val, datetime.date):
        return val.strftime("%Y/%m/%d")
    s = str(val).strip()
    if not s or s.lower() in {"none", "nat", "nan", "null"}:
        return hoje
    formatos = ["%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"]
    for fmt in formatos:
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y/%m/%d")
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return dt.strftime("%Y/%m/%d") if pd.notna(dt) else hoje
    except Exception:
        return hoje

def format_data_br(val):
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    s = str(val).strip()
    if not s or s.lower() in {"none", "nat", "nan", "null"}:
        return ""
    return parse_date_str(val)

def parse_money(val):
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('R$', '').strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        import re
        cleaned = re.sub(r'[^\d.]', '', s)
        return float(cleaned) if cleaned else 0.0

def get_numeric_series(df: pd.DataFrame, col_name: str, default_value: float = 0.0) -> pd.Series:
    if df.empty or col_name not in df.columns:
        return pd.Series([default_value] * len(df), index=df.index, dtype=float)
    return df[col_name].apply(parse_money)

def fetch_data(table_name: str) -> pd.DataFrame:
    local_df = carregar_vendas_local() if table_name == "vendas" else pd.DataFrame()
    if not supabase:
        return local_df if table_name == "vendas" else pd.DataFrame()
    try:
        res = supabase.table(table_name).select("*").execute()
        remote_df = pd.DataFrame(res.data)
        if table_name != "vendas" or local_df.empty:
            return remote_df
        return remote_df
    except Exception as e:
        err_str = str(e)
        if "PGRST205" not in err_str and "schema cache" not in err_str:
            st.warning(f"Aviso de leitura na tabela `{table_name}`: {e}")
        return local_df if table_name == "vendas" else pd.DataFrame()

def normalizar_df_vendas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df_res = df.copy()
    col_v = "valor_venda" if "valor_venda" in df_res.columns else ("valor" if "valor" in df_res.columns else "valor_total")
    df_res["valor_bruto_calc"] = get_numeric_series(df_res, col_v)
    
    t_vals = pd.Series([0.0] * len(df_res), index=df_res.index, dtype=float)
    for t_col_cand in ["tarifa", "tarifa_bancaria", "tarifa_cartao"]:
        if t_col_cand in df_res.columns:
            vals_cand = get_numeric_series(df_res, t_col_cand)
            t_vals = t_vals.where(t_vals > 0, vals_cand)
    df_res["tarifa_calc"] = t_vals

    if "valor_recebido" in df_res.columns:
        val_rec_raw = get_numeric_series(df_res, "valor_recebido")
        df_res["liquido_recebido_calc"] = val_rec_raw.where(val_rec_raw > 0, df_res["valor_bruto_calc"] - df_res["tarifa_calc"])
    else:
        df_res["liquido_recebido_calc"] = df_res["valor_bruto_calc"] - df_res["tarifa_calc"]

    return df_res

def sqlite_insert_record(table_name: str, payload: dict):
    if table_name not in {"pedidos", "vendas"}:
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = {row[1] for row in cur.fetchall()}
        dados = {k: v for k, v in payload.items() if k in cols}
        if not dados:
            return False
        colunas = list(dados.keys())
        placeholders = ", ".join(["?"] * len(colunas))
        cur.execute(
            f"INSERT INTO {table_name} ({', '.join(colunas)}) VALUES ({placeholders})",
            [dados[c] for c in colunas]
        )
        conn.commit()
        return True
    except Exception as exc:
        st.error(f"Erro ao gravar localmente na tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def sqlite_update_record(table_name: str, record_id, payload: dict):
    if table_name not in {"vendas", "pedidos"} or record_id in (None, ""):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = {row[1] for row in cur.fetchall()}
        dados = {k: v for k, v in payload.items() if k in cols and k != "id"}
        if not dados:
            return False
        assignments = ", ".join([f"{c} = ?" for c in dados])
        cur.execute(
            f"UPDATE {table_name} SET {assignments} WHERE id = ?",
            [dados[c] for c in dados] + [record_id]
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        st.error(f"Erro ao atualizar localmente a tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def sqlite_delete_record(table_name: str, record_id):
    if table_name not in {"vendas", "pedidos"} or record_id in (None, ""):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        st.error(f"Erro ao excluir localmente da tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def carregar_vendas_local() -> pd.DataFrame:
    try:
        return carregar_dataframe("SELECT * FROM vendas ORDER BY id DESC")
    except Exception:
        return pd.DataFrame()

def safe_insert(table_name: str, payload: dict):
    if not supabase:
        if table_name in {"pedidos", "vendas"}:
            return sqlite_insert_record(table_name, payload)
        return False
    try:
        supabase.table(table_name).insert(payload).execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "PGRST205" in err_str and table_name in {"pedidos", "vendas"}:
            return sqlite_insert_record(table_name, payload)
        if "PGRST205" in err_str or "custos_avulsos" in err_str or "baixas_estoque" in err_str or "devolucoes_vendas" in err_str:
            if table_name == "custos_avulsos":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["custos_avulsos_local"]) + 1000
                st.session_state["custos_avulsos_local"].append(payload_copy)
                return True
            if table_name == "baixas_estoque":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["baixas_estoque_local"]) + 1000
                st.session_state["baixas_estoque_local"].append(payload_copy)
                return True
            if table_name == "devolucoes_vendas":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["devolucoes_venda_local"]) + 1000
                st.session_state["devolucoes_venda_local"].append(payload_copy)
                return True
        if "Could not find the '" in err_str and "' column" in err_str:
            col_err = err_str.split("Could not find the '")[1].split("' column")[0]
            if col_err in payload:
                payload_retry = payload.copy()
                del payload_retry[col_err]
                return safe_insert(table_name, payload_retry)
        return sqlite_insert_record(table_name, payload) if table_name in {"pedidos", "vendas"} else False

def safe_update_venda(venda_id, payload: dict):
    if venda_id in (None, ""):
        return False
    if not supabase:
        return sqlite_update_record("vendas", venda_id, payload)
    try:
        supabase.table("vendas").update(payload).eq("id", venda_id).execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "PGRST205" in err_str or "schema cache" in err_str:
            return sqlite_update_record("vendas", venda_id, payload)
        return sqlite_update_record("vendas", venda_id, payload)

def safe_delete_venda(venda_id):
    if venda_id in (None, ""):
        return False
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    if supabase:
        try:
            supabase.table("vendas").delete().eq("id", venda_id).execute()
        except Exception:
            pass

    return True

def atualizar_caixa_da_venda(venda_antiga: dict, venda_nova: dict | None = None, excluir: bool = False):
    data_rec = venda_antiga.get("data_recebimento") or venda_antiga.get("data")
    codigo = str(venda_antiga.get("codigo_bone", venda_antiga.get("codigo", ""))).strip()
    cliente = str(venda_antiga.get("cliente", "")).strip()
    qtd = int(pd.to_numeric(venda_antiga.get("qtd", 1), errors="coerce") or 1)
    desc_antiga = f"Venda {codigo} ({qtd}un) - {cliente}"
    if not data_rec or not codigo:
        return

    if not supabase:
        return
    try:
        if excluir:
            supabase.table("caixa").delete().eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
        elif venda_nova is not None:
            data_nova = venda_nova.get("data_recebimento") or venda_nova.get("data")
            v_bruto_n = float(venda_nova.get("valor_venda", 0) or 0)
            t_n = float(venda_nova.get("tarifa", venda_nova.get("tarifa_bancaria", venda_nova.get("tarifa_cartao", 0))) or 0)
            valor_novo = float(venda_nova.get("valor_recebido", v_bruto_n - t_n) or (v_bruto_n - t_n))
            codigo_novo = str(venda_nova.get("codigo_bone", codigo)).strip()
            cliente_novo = str(venda_nova.get("cliente", cliente)).strip()
            qtd_nova = int(pd.to_numeric(venda_nova.get("qtd", qtd), errors="coerce") or qtd)
            desc_nova = f"Venda {codigo_novo} ({qtd_nova}un) - {cliente_novo}"
            if data_nova:
                supabase.table("caixa").update({
                    "data": parse_date_str(data_nova),
                    "desc": desc_nova,
                    "tipo": "Venda",
                    "valor": valor_novo
                }).eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
            else:
                supabase.table("caixa").delete().eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
    except Exception:
        pass

def safe_upsert_produto(payload: dict):
    if not supabase:
        return False

    cod = payload.get("codigo")
    if cod:
        st.session_state["extra_costs_cache"][cod] = {
            "estampa_extra": payload.get("estampa_extra", 0.0),
            "matriz_bordado": payload.get("matriz_bordado", 0.0),
            "data_aquisicao": payload.get("data_aquisicao", "")
        }

    payload_db = payload.copy()
    
    try:
        supabase.table("produtos").upsert(payload_db, on_conflict="codigo").execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "Could not find the '" in err_str and "' column" in err_str:
            col_err = err_str.split("Could not find the '")[1].split("' column")[0]
            if col_err in payload_db:
                del payload_db[col_err]
                return safe_upsert_produto(payload_db)
        elif "PGRST204" in err_str or "PGRST205" in err_str or "schema cache" in err_str:
            for col_opt in ["estampa_extra", "matriz_bordado", "data_aquisicao", "qtd_comprada"]:
                if col_opt in payload_db:
                    del payload_db[col_opt]
            try:
                supabase.table("produtos").upsert(payload_db, on_conflict="codigo").execute()
                return True
            except Exception as inner_err:
                st.error(f"Erro ao salvar produto: {inner_err}")
                return False
        st.error(f"Erro ao atualizar o produto `{payload.get('codigo')}`: {err}")
        return False

def dar_baixa_estoque_venda(codigo_prod, qtd_venda=1):
    if not codigo_prod or qtd_venda <= 0:
        return False
    
    if supabase:
        try:
            res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
            if res_p.data and len(res_p.data) > 0:
                prod_row = res_p.data[0]
                col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
                qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
                novo_estoque = max(0, qtd_atual - int(qtd_venda))
                supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
        except Exception:
            pass

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {row[1] for row in cur.fetchall()}
        if cols:
            col_qtd_sql = "qtd_estoque" if "qtd_estoque" in cols else ("qtd" if "qtd" in cols else "estoque")
            cur.execute(f"SELECT {col_qtd_sql} FROM produtos WHERE codigo = ?", (codigo_prod,))
            row_p = cur.fetchone()
            if row_p:
                qtd_atual_sql = int(pd.to_numeric(row_p[0], errors="coerce") or 0)
                novo_estoque_sql = max(0, qtd_atual_sql - int(qtd_venda))
                cur.execute(f"UPDATE produtos SET {col_qtd_sql} = ? WHERE codigo = ?", (novo_estoque_sql, codigo_prod))
                conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()

    return True

def estornar_estoque(codigo_prod, qtd_estorno):
    if not codigo_prod or qtd_estorno <= 0:
        return False
    
    if supabase:
        try:
            res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
            if res_p.data and len(res_p.data) > 0:
                prod_row = res_p.data[0]
                col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
                qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
                novo_estoque = qtd_atual + int(qtd_estorno)
                supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
        except Exception:
            pass

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {row[1] for row in cur.fetchall()}
        if cols:
            col_qtd_sql = "qtd_estoque" if "qtd_estoque" in cols else ("qtd" if "qtd" in cols else "estoque")
            cur.execute(f"SELECT {col_qtd_sql} FROM produtos WHERE codigo = ?", (codigo_prod,))
            row_p = cur.fetchone()
            if row_p:
                qtd_atual_sql = int(pd.to_numeric(row_p[0], errors="coerce") or 0)
                novo_estoque_sql = qtd_atual_sql + int(qtd_estorno)
                cur.execute(f"UPDATE produtos SET {col_qtd_sql} = ? WHERE codigo = ?", (novo_estoque_sql, codigo_prod))
                conn.commit()
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS produtos (
                    codigo TEXT PRIMARY KEY,
                    cor TEXT,
                    frase TEXT,
                    cor_estampa TEXT,
                    categoria TEXT,
                    custo REAL,
                    qtd_estoque INTEGER DEFAULT 1
                )
            ''')
            cur.execute("INSERT OR REPLACE INTO produtos (codigo, qtd_estoque) VALUES (?, ?)", (codigo_prod, int(qtd_estorno)))
            conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()

    return True

@st.cache_data(ttl=600)
def get_saved_logo():
    if not supabase:
        return None
    try:
        res = supabase.table("configuracoes").select("valor_b64").eq("chave", "logo_header").execute()
        if res.data and len(res.data) > 0:
            val = res.data[0].get("valor_b64")
            if val and val.startswith("data:image"):
                return val
    except Exception:
        pass
    return None

def save_logo_to_db(b64_data_url):
    if not supabase:
        return False
    try:
        supabase.table("configuracoes").upsert(
            {"chave": "logo_header", "valor_b64": b64_data_url}, 
            on_conflict="chave"
        ).execute()
        get_saved_logo.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar logo: {e}")
        return False

def delete_logo_from_db():
    if not supabase:
        return
    try:
        supabase.table("configuracoes").delete().eq("chave", "logo_header").execute()
        get_saved_logo.clear()
    except Exception as e:
        st.error(f"Erro ao remover logo: {e}")

def get_ultimo_codigo_config():
    if supabase:
        try:
            res = supabase.table("configuracoes").select("valor_b64").eq("chave", "ultimo_codigo_bone").execute()
            if res.data and len(res.data) > 0:
                val = res.data[0].get("valor_b64")
                if val:
                    return str(val).strip()
        except Exception:
            pass
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT valor_b64 FROM configuracoes WHERE chave = 'ultimo_codigo_bone'")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    return "BL-0001"

def set_ultimo_codigo_config(novo_codigo):
    novo_codigo = str(novo_codigo).strip()
    if supabase:
        try:
            supabase.table("configuracoes").upsert(
                {"chave": "ultimo_codigo_bone", "valor_b64": novo_codigo},
                on_conflict="chave"
            ).execute()
        except Exception as e:
            st.error(f"Erro ao salvar configuração do código no Supabase: {e}")
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO configuracoes (chave, valor_b64) VALUES ('ultimo_codigo_bone', ?)", (novo_codigo,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar configuração do código localmente: {e}")
        return False

def gerar_proximo_codigo(codigo_atual):
    codigo_atual = str(codigo_atual).strip()
    import re
    try:
        match = re.search(r'^(.*?)[-_]?(\d+)$', codigo_atual)
        if match:
            prefixo = match.group(1)
            num_str = match.group(2)
            proximo_num = int(num_str) + 1
            tam_num = len(num_str)
            sep = "-" if "-" in codigo_atual else ("_" if "_" in codigo_atual else "")
            return f"{prefixo}{sep}{proximo_num:0{tam_num}d}" if sep else f"{prefixo}{proximo_num:0{tam_num}d}"
        else:
            return f"{codigo_atual}-0001"
    except Exception:
        return "BL-0002"

def get_df_compra_mercadorias():
    df_ped_ent = carregar_dataframe(
        "SELECT * FROM pedidos WHERE status LIKE '%Entregue%' ORDER BY id DESC"
    )
    if df_ped_ent.empty:
        return pd.DataFrame()
    
    df_ped_ent["preco_num"] = get_numeric_series(df_ped_ent, "preco")
    df_ped_ent["estampa_extra_num"] = get_numeric_series(df_ped_ent, "valor_estampa_extra")
    df_ped_ent["matriz_num"] = get_numeric_series(df_ped_ent, "valor_matriz")
    
    df_ped_ent["total_item_calc"] = (
        df_ped_ent["preco_num"] +
        df_ped_ent["estampa_extra_num"] +
        df_ped_ent["matriz_num"]
    )
    if "total_item" in df_ped_ent.columns:
        total_importado = pd.to_numeric(df_ped_ent["total_item"], errors="coerce")
        df_ped_ent["total_item_calc"] = total_importado.where(total_importado.notna(), df_ped_ent["total_item_calc"])
    
    col_dt = "data_criacao" if "data_criacao" in df_ped_ent.columns else "data"
    
    if "codigo_produto" in df_ped_ent.columns:
        codigos_col = df_ped_ent["codigo_produto"].fillna(get_ultimo_codigo_config())
    else:
        codigos_col = get_ultimo_codigo_config()

    df_cm = pd.DataFrame({
        "id": df_ped_ent.get("id"),
        "Data_Raw": df_ped_ent.get(col_dt, ""),
        "Data": df_ped_ent[col_dt].apply(format_data_br) if col_dt in df_ped_ent.columns else "",
        "Código": codigos_col,
        "Cor do Boné": df_ped_ent.get("cor_bone", ""),
        "Arte Estampada": df_ped_ent.get("frase_arte", ""),
        "Cor da Estampa": df_ped_ent.get("cor_linha", ""),
        "Produto": df_ped_ent.get("tipo", ""),
        "preco_num": df_ped_ent["preco_num"],
        "estampa_extra_num": df_ped_ent["estampa_extra_num"],
        "matriz_num": df_ped_ent["matriz_num"],
        "total_item_calc": df_ped_ent["total_item_calc"]
    })
    return df_cm

def calcular_saldo_final_fluxo_caixa(df_vendas_in, df_custos_in, df_aportes_in, df_devolucoes_in):
    lista_movimentos = []

    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        agrup_cm = df_cm.groupby("data_str").agg(total_custo=("total_item_calc", "sum")).reset_index()
        for _, r in agrup_cm.iterrows():
            tot_c = float(r["total_custo"])
            if tot_c > 0:
                lista_movimentos.append({"Data_Val": r["data_str"], "Valor_Num": -tot_c})

    if not df_vendas_in.empty:
        df_v_norm = normalizar_df_vendas(df_vendas_in)
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_v_norm.columns else None
        if col_dt_rec:
            df_v_recebidas = df_v_norm[df_v_norm[col_dt_rec].notna() & df_v_norm[col_dt_rec].astype(str).str.strip().ne("") & df_v_norm[col_dt_rec].astype(str).str.lower().ne("none")].copy()
            for _, r in df_v_recebidas.iterrows():
                dt_rec_val = r.get(col_dt_rec)
                val_v_calc = float(r.get("liquido_recebido_calc", 0.0))
                if val_v_calc > 0:
                    lista_movimentos.append({"Data_Val": parse_date_str(dt_rec_val), "Valor_Num": val_v_calc})

    if not df_custos_in.empty:
        for _, r in df_custos_in.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            if val_c > 0:
                lista_movimentos.append({"Data_Val": parse_date_str(r.get("data")), "Valor_Num": -val_c})

    if not df_aportes_in.empty:
        for _, r in df_aportes_in.iterrows():
            val_ap = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            tipo_ap = str(r.get("tipo", ""))
            if val_ap != 0:
                is_devolucao = "devoluc" in tipo_ap.lower() or val_ap < 0
                val_final = -abs(val_ap) if is_devolucao else abs(val_ap)
                dt_ap_raw = r.get("data") or r.get("data_aporte") or r.get("created_at")
                dt_ap_str = parse_date_str(dt_ap_raw) if dt_ap_raw else datetime.date.today().strftime("%Y-%m-%d")
                lista_movimentos.append({"Data_Val": dt_ap_str, "Valor_Num": val_final})

    if not df_devolucoes_in.empty:
        for _, r in df_devolucoes_in.iterrows():
            val_dev = float(pd.to_numeric(r.get("valor_devolvido", 0.0), errors="coerce") or 0.0)
            if val_dev > 0:
                dt_dev_raw = r.get("data_devolucao")
                dt_dev_str = parse_date_str(dt_dev_raw) if dt_dev_raw else datetime.date.today().strftime("%Y-%m-%d")
                lista_movimentos.append({"Data_Val": dt_dev_str, "Valor_Num": -val_dev})

    # Adicionar também dados da tabela caixa remota/local se houver
    df_caixa_tab = fetch_data("caixa")
    if not df_caixa_tab.empty:
        for _, r in df_caixa_tab.iterrows():
            val_cx = float(pd.to_numeric(r.get("valor", r.get("ENTRADA R$", 0) or 0), errors="coerce") or 0.0)
            dt_cx = parse_date_str(r.get("data", r.get("DATA")))
            if val_cx != 0:
                lista_movimentos.append({"Data_Val": dt_cx, "Valor_Num": val_cx})

    if lista_movimentos:
        df_ext = pd.DataFrame(lista_movimentos)
        return float(df_ext["Valor_Num"].sum())
    return 0.0

# Carregar tabelas do Supabase
df_produtos = fetch_data("produtos")

CODIGOS_REMOVER = ["BL-0001", "BL-0002", "BL-0003", "BL-0004", "Teste1", "Teste 1"]
if not df_produtos.empty and "codigo" in df_produtos.columns:
    df_produtos = df_produtos[~df_produtos["codigo"].astype(str).str.strip().isin(CODIGOS_REMOVER)].reset_index(drop=True)

df_vendas = fetch_data("vendas")
if df_vendas.empty:
    df_vendas = carregar_vendas_local()
if not df_vendas.empty:
    col_c_v = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
    if col_c_v in df_vendas.columns:
        df_vendas = df_vendas[~df_vendas[col_c_v].astype(str).str.strip().isin(CODIGOS_REMOVER)].reset_index(drop=True)

df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")
df_baixas = fetch_data("baixas_estoque")
df_devolucoes = fetch_data("devolucoes_vendas")

if not st.session_state["custos_avulsos_local"]:
    pass
else:
    df_custos_loc = pd.DataFrame(st.session_state["custos_avulsos_local"])
    df_custos = pd.concat([df_custos, df_custos_loc], ignore_index=True) if not df_custos.empty else df_custos_loc

if "flash_success" in st.session_state and st.session_state["flash_success"]:
    st.success(st.session_state["flash_success"])
    st.session_state["flash_success"] = None

if "current_logo" not in st.session_state:
    st.session_state["current_logo"] = get_saved_logo()

# 3. Sidebar (Barra Lateral)
with st.sidebar:
    st.markdown("### 📌 Módulos do Sistema")
    menu = st.radio(
        "Navegue entre os módulos:",
        ["📈 Dashboard", "📦 Pedidos", "🛍 Compra de Mercadorias", "📦 Estoque", "🛒 Vendas", "💰 Contas a Receber", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "💾 Gestão de Dados", "⚙ Configuração"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    
    with st.expander("🎨 Personalização", expanded=False):
        uploaded_logo = st.file_uploader(
            "Carregar Nova Logo da Marca", 
            type=["png", "jpg", "jpeg", "webp", "svg"],
            help="Envie a logomarca para fixar permanentemente no topo do site."
        )
        if uploaded_logo is not None:
            with st.spinner("Processando e salvando imagem..."):
                bytes_data = uploaded_logo.getvalue()
                b64_str = base64.b64encode(bytes_data).decode("utf-8")
                mime_type = uploaded_logo.type or "image/png"
                data_url = f"data:{mime_type};base64,{b64_str}"
                
                if save_logo_to_db(data_url):
                    st.session_state["current_logo"] = data_url
                    st.success("Logo fixa salva e aplicada!")
                    st.rerun()

        if st.session_state.get("current_logo") is not None:
            if st.button("🗑 Excluir Logo Atual", use_container_width=True, type="secondary"):
                delete_logo_from_db()
                st.session_state["current_logo"] = None
                st.success("Logo removida permanentemente!")
                st.rerun()

# 4. Exibição do Cabeçalho
active_logo = st.session_state.get("current_logo")
if active_logo:
    st.image(active_logo, use_container_width=True)
else:
    st.markdown("""
    <div class="custom-header-container">
        <span style="font-size: 3.2em; margin-right: 10px;">🧢</span>
        <div class="header-text">
            <h1>R² Bonés — Sistema Gerencial Pro</h1>
            <p>Vista o que você pensa • Painel de Controle Operacional</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 5. Módulos do Sistema

if "Dashboard" in menu:
    st.subheader("📈 Dashboard Executivo")
    
    col_v_val = "valor_venda" if "valor_venda" in df_vendas.columns else ("valor" if "valor" in df_vendas.columns else ("valor_total" if "valor_total" in df_vendas.columns else None))
    total_faturado = float(df_vendas[col_v_val].sum()) if not df_vendas.empty and col_v_val else 0.0
    
    total_cmv = 0.0
    if not df_vendas.empty:
        df_cm_ref = get_df_compra_mercadorias()
        if not df_cm_ref.empty:
            c_v_col = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
            df_v_cm = df_vendas.merge(df_cm_ref, left_on=c_v_col, right_on="Código", how="inner")
            if "total_item_calc" in df_v_cm.columns:
                col_q = "qtd" if "qtd" in df_v_cm.columns else ("quantidade" if "quantidade" in df_v_cm.columns else None)
                qtds = get_numeric_series(df_v_cm, col_q, 1.0) if col_q else 1.0
                total_cmv = float((df_v_cm["total_item_calc"] * qtds).sum())

    saldo_caixa = calcular_saldo_final_fluxo_caixa(df_vendas, df_custos, df_aportes, df_devolucoes)

    total_qtd_vendida = 0
    if not df_vendas.empty:
        col_q_venda = "qtd" if "qtd" in df_vendas.columns else ("quantidade" if "quantidade" in df_vendas.columns else None)
        if col_q_venda:
            total_qtd_vendida = int(get_numeric_series(df_vendas, col_q_venda).sum())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV TOTAL <span class="tooltip-icon" title="Custo das mercadorias vendidas obtido do menu Compra de Mercadoria">ℹ</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo final vindo do menu Fluxo de Caixa">ℹ</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Quantidade Vendida <span class="tooltip-icon" title="Quantidade total de peças/bonés faturados nas vendas">ℹ</span></div><div class="kpi-value">{total_qtd_vendida} un</div></div>', unsafe_allow_html=True)

elif "Compra de Mercadorias" in menu:
    st.subheader("🛍 Relatório de Compra de Mercadorias")
    df_cm = get_df_compra_mercadorias()
    if df_cm.empty:
        st.info("Nenhum pedido entregue disponível para o relatório de compra de mercadorias.")
    else:
        df_cm["Mes_Ano"] = pd.to_datetime(df_cm["Data_Raw"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
        for mes in sorted(df_cm["Mes_Ano"].unique(), reverse=True):
            df_mes_cm = df_cm[df_cm["Mes_Ano"] == mes].copy()
            with st.expander(f"📅 Período / Mês: {mes} ({len(df_mes_cm)} itens)", expanded=True):
                df_relatorio = pd.DataFrame({
                    "Data": df_mes_cm["Data"],
                    "Código": df_mes_cm["Código"],
                    "Cor do Boné": df_mes_cm["Cor do Boné"],
                    "Arte Estampada": df_mes_cm["Arte Estampada"],
                    "Cor da Estampa": df_mes_cm["Cor da Estampa"],
                    "Produto": df_mes_cm["Produto"],
                    "Preço Base": df_mes_cm["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Estampa Extra": df_mes_cm["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Matriz Bordado": df_mes_cm["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Total Item": df_mes_cm["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                })
                st.dataframe(df_relatorio, use_container_width=True, hide_index=True)

elif "Pedidos" in menu:
    st.subheader("📦 Gerenciamento de Pedidos e Encomendas")
    df_todos_pedidos = carregar_dataframe("SELECT * FROM pedidos ORDER BY id DESC")
    with st.expander("➕ Cadastrar Novo Item no Pedido (Manual)", expanded=False):
        with st.form("form_novo_pedido_manual"):
            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                lote_m = st.text_input("Identificador / Lote do Pedido *", value="Pedido #3.10-2026")
                cor_b_m = st.text_input("Cor do Boné *", value="")
            with c_p2:
                arte_m = st.text_input("Arte Estampada *", value="")
                cor_e_m = st.text_input("Cor da Estampa", value="")
            with c_p3:
                prod_m = st.selectbox("Produto *", ["Básico", "Kids", "Outro", "Premium"])
                preco_m = st.number_input("Preço Base (R$) *", min_value=0.0, value=29.0, format="%.2f")
            
            c_ex1, c_ex2, c_ex3 = st.columns(3)
            with c_ex1:
                v_extra_m = st.number_input("Estampa Extra (R$)", min_value=0.0, value=0.0, format="%.2f")
            with c_ex2:
                v_matriz_m = st.number_input("Matriz Bordado (R$)", min_value=0.0, value=0.0, format="%.2f")
            with c_ex3:
                dt_p_m = st.date_input("Data da Criação *", datetime.date.today(), format="YYYY/MM/DD")
            
            obs_p_m = st.text_area("Observações do Pedido", value="")
            btn_cadastrar_p = st.form_submit_button("💾 Cadastrar Item", use_container_width=True, type="primary")
            if btn_cadastrar_p:
                if not lote_m.strip() or not cor_b_m.strip() or not arte_m.strip():
                    st.error("Preencha os campos obrigatórios!")
                else:
                    payload_pedido = {
                        "lote_id": lote_m.strip(),
                        "data_criacao": parse_date_str(dt_p_m),
                        "cor_bone": cor_b_m.strip(),
                        "frase_arte": arte_m.strip(),
                        "cor_linha": cor_e_m.strip(),
                        "tipo": prod_m,
                        "preco": preco_m,
                        "observacoes": obs_p_m.strip(),
                        "status": "Em Produção",
                        "valor_estampa_extra": v_extra_m,
                        "valor_matriz": v_matriz_m,
                        "total_item": round(preco_m + v_extra_m + v_matriz_m, 2)
                    }
                    safe_insert("pedidos", payload_pedido)
                    st.session_state["flash_success"] = "🎉 Item cadastrado com sucesso!"
                    st.rerun()

elif "Estoque" in menu:
    st.subheader("📦 Estoque Atual")
    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_est = df_cm.copy()
        if not df_produtos.empty and "codigo" in df_produtos.columns:
            col_qtd_p = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
            df_est = df_est.merge(df_produtos[["codigo", col_qtd_p]], left_on="Código", right_on="codigo", how="left")
            df_est["Estoque"] = pd.to_numeric(df_est[col_qtd_p], errors="coerce").fillna(1).astype(int)
        else:
            df_est["Estoque"] = 1
        df_est = df_est[df_est["Estoque"] > 0].copy()
        st.markdown(f"#### 📊 **Quantidade Total em Estoque:** `{int(df_est['Estoque'].sum())} un`")
        
        df_est["Custo Base"] = df_est["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est["Custo Total"] = df_est["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
        st.dataframe(df_est[["Código", "Cor do Boné", "Arte Estampada", "Produto", "Estoque", "Custo Total"]], use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif "Vendas" in menu:
    st.subheader("🛒 Lançar Nova Venda")
    df_cm_estoque = get_df_compra_mercadorias()
    map_estoque_disponivel = {}
    opts = []
    if not df_cm_estoque.empty:
        df_cm_estoque = df_cm_estoque[~df_cm_estoque["Código"].isin(CODIGOS_REMOVER)]
        if not df_produtos.empty and "codigo" in df_produtos.columns:
            col_q = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
            df_cm_estoque = df_cm_estoque.merge(df_produtos[["codigo", col_q]], left_on="Código", right_on="codigo", how="left")
            df_cm_estoque["qtd_disp"] = pd.to_numeric(df_cm_estoque[col_q], errors="coerce").fillna(1).astype(int)
        else:
            df_cm_estoque["qtd_disp"] = 1
        
        for _, r in df_cm_estoque[df_cm_estoque["qtd_disp"] > 0].iterrows():
            cod_item = r['Código']
            q_disp = int(r['qtd_disp'])
            map_estoque_disponivel[cod_item] = q_disp
            opts.append(f"[{cod_item}] \"{r.get('Arte Estampada','')}\" - Cor: {r.get('Cor do Boné','')} (Disponível: {q_disp} un)")

    if not opts:
        st.warning("⚠ Nenhum boné disponível em estoque para venda no momento.")
        codigo_sel = ""
    else:
        prod_sel = st.selectbox("🔍 Selecione/Pesquise o Boné no Estoque:", opts)
        codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""

    max_qtd_permitida = map_estoque_disponivel.get(codigo_sel, 1) if codigo_sel else 1

    c1, c2, c3 = st.columns(3)
    with c1:
        qtd_venda = st.number_input("Quantidade *", min_value=1, max_value=max_qtd_permitida, value=1, step=1)
        cliente = st.text_input("Nome do Cliente *")
    with c2:
        valor_venda = st.number_input("Valor de Venda Bruto (R$) *", min_value=0.0, value=0.0, step=5.0, format="%.2f")
        tarifa_venda = st.number_input("Tarifa / Taxa Bancária (R$)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    with c3:
        forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])

    valor_liquido_calc = max(0.0, float(valor_venda) - float(tarifa_venda))
    st.markdown(f"👉 **Valor Bruto:** `R$ {float(valor_venda):,.2f}` | 🏷 **Tarifa:** `R$ {float(tarifa_venda):,.2f}` | 💵 **Valor Líquido:** `R$ {valor_liquido_calc:,.2f}`")

    if st.button("🚀 Finalizar Venda Individual", type="primary", use_container_width=True):
        if not cliente.strip() or not codigo_sel.strip():
            st.error("Preencha o cliente e selecione o produto!")
        else:
            data_atual_str = datetime.date.today().strftime("%Y/%m/%d")
            payload_venda = {
                "codigo_bone": codigo_sel.strip(),
                "codigo": codigo_sel.strip(),
                "cliente": cliente.strip(),
                "qtd": int(qtd_venda),
                "valor_venda": round(float(valor_venda), 2),
                "tarifa": round(float(tarifa_venda), 2),
                "tarifa_bancaria": round(float(tarifa_venda), 2),
                "tarifa_cartao": round(float(tarifa_venda), 2),
                "valor_recebido": round(valor_liquido_calc, 2),
                "forma_pagto": forma_pagto,
                "data": data_atual_str,
                "data_venda": data_atual_str,
                "data_recebimento": None
            }
            if safe_insert("vendas", payload_venda):
                dar_baixa_estoque_venda(codigo_sel.strip(), int(qtd_venda))
                st.session_state["flash_success"] = "🎉 Venda salva e encaminhada para 'Contas a Receber'!"
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Histórico Detalhado de Vendas")
    df_historico_vendas = fetch_data("vendas")
    if df_historico_vendas.empty:
        df_historico_vendas = carregar_vendas_local()
    if not df_historico_vendas.empty:
        df_historico_vendas = normalizar_df_vendas(df_historico_vendas)
        for _, venda_row in df_historico_vendas.iterrows():
            v_id = venda_row.get("id")
            v_cod = str(venda_row.get("codigo_bone", venda_row.get("codigo", "")))
            v_cli = str(venda_row.get("cliente", ""))
            v_bruto = parse_money(venda_row.get("valor_venda", 0))
            v_tar = float(venda_row.get("tarifa_calc", 0))
            v_liq = max(0.0, v_bruto - v_tar)
            resumo_str = f"👉 Valor Bruto: R$ {v_bruto:,.2f} | 🏷 Tarifa: R$ {v_tar:,.2f} | 💵 Valor Líquido: R$ {v_liq:,.2f}"
            st.write(f"ID #{v_id} | `{v_cod}` | **{v_cli}** | {resumo_str}")

elif "Contas a Receber" in menu:
    st.subheader("💰 Contas a Receber")
    df_cr = fetch_data("vendas")
    if df_cr.empty:
        df_cr = carregar_vendas_local()
    if not df_cr.empty:
        df_cr = normalizar_df_vendas(df_cr)
        df_pendentes = df_cr[df_cr["data_recebimento"].isna() | df_cr["data_recebimento"].astype(str).str.strip().isin(["", "None", "nan", "NaT"])].copy()
        if not df_pendentes.empty:
            for _, r in df_pendentes.iterrows():
                v_id = r.get("id")
                v_bruto = parse_money(r.get("valor_venda", 0))
                v_tar = float(r.get("tarifa_calc", 0))
                v_liq = max(0.0, v_bruto - v_tar)
                with st.container(border=True):
                    st.write(f"Venda ID #{v_id} | Cliente: **{r.get('cliente')}** | Líquido: R$ {v_liq:,.2f}")
                    dt_rec = st.date_input("Data de Recebimento", datetime.date.today(), format="YYYY/MM/DD", key=f"dt_rec_{v_id}")
                    if st.button("✅ Confirmar Recebimento", key=f"btn_rec_{v_id}", type="primary"):
                        dt_str = parse_date_str(dt_rec)
                        safe_update_venda(v_id, {"data_recebimento": dt_str, "valor_recebido": round(v_liq, 2)})
                        safe_insert("caixa", {"data": dt_str, "desc": f"Venda {r.get('codigo')} - {r.get('cliente')}", "tipo": "Venda", "valor": round(v_liq, 2)})
                        st.session_state["flash_success"] = "Recebimento confirmado e lançado no Fluxo de Caixa!"
                        st.rerun()
        else:
            st.info("Nenhuma venda pendente!")

elif "Custos" in menu:
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "💳 Tarifas"], horizontal=True)
    if "Tarifas" in sub_tab:
        st.markdown("##### 💳 Demonstrativo Detalhado de Tarifas Descontadas nas Vendas")
        df_v_tarifas = fetch_data("vendas")
        if df_v_tarifas.empty:
            df_v_tarifas = carregar_vendas_local()
        if not df_v_tarifas.empty:
            df_v_tarifas = normalizar_df_vendas(df_v_tarifas)
            df_t_com_valor = df_v_tarifas[df_v_tarifas["tarifa_calc"] > 0].copy()
            if not df_t_com_valor.empty:
                st.dataframe(df_t_com_valor[["codigo", "cliente", "valor_bruto_calc", "tarifa_calc", "liquido_recebido_calc"]], use_container_width=True, hide_index=True)
                st.markdown(f"### Total Acumulado de Tarifas: `R$ {df_t_com_valor['tarifa_calc'].sum():,.2f}`")
            else:
                st.info("Nenhuma tarifa registrada.")

elif "Fluxo de Caixa" in menu or "Caixa" in menu:
    st.subheader("💰 Extrato Consolidado de Fluxo de Caixa")
    lista_movimentos = []

    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        for _, r in df_cm.groupby("data_str").agg(total_custo=("total_item_calc", "sum")).reset_index().iterrows():
            if float(r["total_custo"]) > 0:
                lista_movimentos.append({"Data_Val": r["data_str"], "Origem": "🛍 Compra de Mercadorias", "Descrição": "Compra Agrupada", "Tipo": "Saída 🔴", "Valor_Num": -float(r["total_custo"])})

    df_v_rec = fetch_data("vendas")
    if not df_v_rec.empty:
        df_v_rec = normalizar_df_vendas(df_v_rec)
        for _, r in df_v_rec[df_v_rec["data_recebimento"].notna() & df_v_rec["data_recebimento"].astype(str).str.strip().ne("")].iterrows():
            val_liq = float(r.get("liquido_recebido_calc", 0))
            if val_liq > 0:
                lista_movimentos.append({"Data_Val": parse_date_str(r.get("data_recebimento")), "Origem": "🛒 Recebimento de Vendas", "Descrição": f"Venda {r.get('codigo')} - {r.get('cliente')}", "Tipo": "Entrada 🟢", "Valor_Num": val_liq})

    df_cx_tab = fetch_data("caixa")
    if not df_cx_tab.empty:
        for _, r in df_cx_tab.iterrows():
            v_cx = float(pd.to_numeric(r.get("valor", r.get("ENTRADA R$", 0) or 0), errors="coerce") or 0.0)
            if v_cx != 0:
                dt_cx = parse_date_str(r.get("data", r.get("DATA")))
                tipo_cx = "Entrada 🟢" if v_cx > 0 else "Saída 🔴"
                lista_movimentos.append({"Data_Val": dt_cx, "Origem": "📁 Lançamento Caixa", "Descrição": str(r.get("desc", r.get("DESCRIÇÃO", "Movimento"))), "Tipo": tipo_cx, "Valor_Num": v_cx})

    if lista_movimentos:
        df_ext = pd.DataFrame(lista_movimentos)
        df_ext["Data_Raw"] = pd.to_datetime(df_ext["Data_Val"].apply(parse_date_str), errors="coerce").fillna(pd.Timestamp.now())
        df_ext["Mes_Ano"] = df_ext["Data_Raw"].dt.strftime("%Y-%m").fillna("Outros")
        df_ext = df_ext.sort_values(by="Data_Raw", ascending=True).reset_index(drop=True)

        meses_caixa = sorted(df_ext["Mes_Ano"].unique(), reverse=False)
        saldo_acumulado_anterior = 0.0

        for mes in meses_caixa:
            df_cx_mes = df_ext[df_ext["Mes_Ano"] == mes].copy()
            st.markdown(f"#### 📅 Mês: {mes.replace('-', '/')}")
            
            linhas_mes_exib = []
            if saldo_acumulado_anterior != 0.0:
                linhas_mes_exib.append({
                    "Data": f"{mes}/01",
                    "Origem": "🟢 SALDO INICIAL",
                    "Descrição": "Saldo transportado do mês anterior",
                    "Tipo": "Saldo 💵",
                    "Valor (R$)": f"R$ {saldo_acumulado_anterior:,.2f}",
                    "Saldo Acumulado (R$)": f"R$ {saldo_acumulado_anterior:,.2f}"
                })
            
            running_mes = saldo_acumulado_anterior
            for _, r_m in df_cx_mes.iterrows():
                running_mes += r_m["Valor_Num"]
                linhas_mes_exib.append({
                    "Data": r_m["Data_Val"],
                    "Origem": r_m["Origem"],
                    "Descrição": r_m["Descrição"],
                    "Tipo": r_m["Tipo"],
                    "Valor (R$)": f"R$ {r_m['Valor_Num']:,.2f}",
                    "Saldo Acumulado (R$)": f"R$ {running_mes:,.2f}"
                })
            
            saldo_final_mes = running_mes
            saldo_acumulado_anterior = saldo_final_mes
            
            try:
                ano_m, mes_m = map(int, mes.split("-"))
                ultimo_dia_num = calendar.monthrange(ano_m, mes_m)[1]
                data_ultimo_dia_mes = f"{mes}/{ultimo_dia_num:02d}"
            except Exception:
                data_ultimo_dia_mes = f"{mes}/30"

            linhas_mes_exib.append({
                "Data": data_ultimo_dia_mes,
                "Origem": "🏁 SALDO FINAL",
                "Descrição": f"Saldo Acumulado Final do Período ({mes})",
                "Tipo": "Saldo 💵",
                "Valor (R$)": f"R$ {saldo_final_mes:,.2f}",
                "Saldo Acumulado (R$)": f"R$ {saldo_final_mes:,.2f}"
            })
            
            st.dataframe(pd.DataFrame(linhas_mes_exib), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação no fluxo de caixa.")

elif "Gestão" in menu or "Dados" in menu:
    st.subheader("💾 Gestão de Dados & Backup")
    st.markdown("Gerencie o banco de dados, faça downloads de segurança e importe diretamente a planilha mestre do sistema (`Bonés (4).xlsx`).")

    col_status, col_export = st.columns(2)

    with col_status:
        st.markdown("#### 📌 Status da Conexão")
        if supabase is not None:
            try:
                supabase.table("produtos").select("id").limit(1).execute()
                st.success("🟢 Conectado ao Supabase (PostgreSQL Nuvem)")
            except Exception as e:
                st.error(f"🔴 Falha ao conectar com o Supabase: {e}")
        else:
            st.error("🔴 Supabase não configurado")

    with col_export:
        st.markdown("#### 📥 Exportar Backup Geral em Excel")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_produtos.to_excel(writer, sheet_name='Produtos_Estoque', index=False)
            df_vendas.to_excel(writer, sheet_name='Vendas', index=False)
            df_caixa.to_excel(writer, sheet_name='Caixa', index=False)
        st.download_button("📥 Baixar Backup Geral (.xlsx)", data=output.getvalue(), file_name="Backup_R2_Bones.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.markdown("---")
    st.markdown("#### 📂 Importar Planilha Mestre ('Bonés (4).xlsx') para o Supabase")
    
    uploaded_planilha_mestre = st.file_uploader("Enviar arquivo 'Bonés (4).xlsx'", type=["xlsx"], key="import_planilha_mestre_supabase")
    
    if uploaded_planilha_mestre is not None:
        if st.button("🚀 Inserir Dados da Planilha Diretamente no Supabase", type="primary", use_container_width=True):
            try:
                xls = pd.ExcelFile(uploaded_planilha_mestre)
                
                # 1. Processar aba Matriz (Produtos e Vendas)
                if 'Matriz' in xls.sheet_names:
                    df_mat = pd.read_excel(xls, sheet_name='Matriz')
                    prods_lote, vendas_lote = [], []
                    
                    for _, row in df_mat.dropna(subset=['CÓDIGO']).iterrows():
                        codigo = str(row['CÓDIGO']).strip()
                        cor = str(row.get('COR', '')).strip()
                        frase = str(row.get('FRASE ESTAMPADA', '')).strip()
                        cor_est = str(row.get('FRASE ESTAMPADA-COR', '')).strip()
                        categoria = str(row.get('CATEGORIA', 'Básico')).strip()
                        custo = float(row.get('Unnamed: 6', 29.0) or 29.0)
                        estoque_qtd = int(row.get('Estoque', 0) or 0)
                        
                        prods_lote.append({
                            "codigo": codigo, "cor": cor, "frase": frase,
                            "cor_estampa": cor_est, "categoria": categoria,
                            "custo": custo, "qtd_estoque": estoque_qtd
                        })
                        
                        data_venda = row.get('Venda')
                        if pd.notna(data_venda):
                            val_v = float(row.get('Unnamed: 9', 0.0) or 0.0)
                            cli = str(row.get('Cliente', '')).strip()
                            rec = row.get('Recebimento')
                            forma = str(row.get('Forma de Receb', 'PIX')).strip()
                            rec_val = float(row.get('Recebido', val_v) or val_v)
                            dt_v = pd.to_datetime(data_venda).strftime("%Y/%m/%d")
                            dt_r = pd.to_datetime(rec).strftime("%Y/%m/%d") if pd.notna(rec) else None
                            
                            vendas_lote.append({
                                "codigo_bone": codigo, "codigo": codigo, "cliente": cli,
                                "qtd": 1, "valor_venda": val_v, "tarifa": 0.0,
                                "tarifa_bancaria": 0.0, "tarifa_cartao": 0.0,
                                "valor_recebido": rec_val, "forma_pagto": forma,
                                "data": dt_v, "data_venda": dt_v, "data_recebimento": dt_r,
                                "custo": custo, "custo_unitario": custo
                            })
                    
                    if supabase and prods_lote:
                        supabase.table("produtos").upsert(prods_lote, on_conflict="codigo").execute()
                    if supabase and vendas_lote:
                        supabase.table("vendas").upsert(vendas_lote).execute()

                # 2. Processar aba Caixa
                if 'Caixa' in xls.sheet_names:
                    df_cx = pd.read_excel(xls, sheet_name='Caixa').dropna(subset=['DATA'])
                    caixa_lote = []
                    for _, row in df_cx.iterrows():
                        dt = pd.to_datetime(row['DATA']).strftime("%Y/%m/%d")
                        desc = str(row.get('DESCRIÇÃO', '')).strip()
                        tipo = str(row.get('TIPO', 'Entrada')).strip()
                        ent = row.get('ENTRADA R$')
                        sai = row.get('SAÍDA R$')
                        val = float(ent) if pd.notna(ent) else -float(sai) if pd.notna(sai) else 0.0
                        caixa_lote.append({"data": dt, "desc": desc, "tipo": tipo, "valor": val})
                    
                    if supabase and caixa_lote:
                        supabase.table("caixa").insert(caixa_lote).execute()

                st.success("🎉 Todos os dados da planilha 'Bonés (4).xlsx' foram inseridos com sucesso no Supabase!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao importar planilha para o Supabase: {e}")

elif "Configuração" in menu or "Configuracao" in menu:
    st.subheader("⚙ Configurações Gerais do Sistema")
    st.markdown("Gerencie parâmetros operacionais do sistema.")
