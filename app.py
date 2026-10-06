import datetime
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
            codigo_produto TEXT
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

    c.execute("UPDATE pedidos SET tipo = 'Básico' WHERE tipo = 'Simples'")
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
# FUNÇÕES ROBUSTAS DE TRATAMENTO E FORMATO DE DATAS (BR)
# ----------------------------------------------------
def parse_date_str(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return datetime.date.today().strftime("%Y-%m-%d")
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    try:
        dt = pd.to_datetime(s, dayfirst=True, format="%d/%m/%Y", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return dt.strftime("%Y-%m-%d") if pd.notna(dt) else datetime.date.today().strftime("%Y-%m-%d")
    except Exception:
        return s

def format_data_br(val):
    if not val or pd.isna(val) or str(val).strip().lower() in ["none", "nat", "nan", ""]:
        return ""
    try:
        dt = pd.to_datetime(val, dayfirst=True, format="%d/%m/%Y", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(val, dayfirst=True, errors="coerce")
        return dt.strftime("%d/%m/%Y") if pd.notna(dt) else str(val)
    except Exception:
        return str(val)

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
    if not supabase:
        return pd.DataFrame()
    try:
        res = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        err_str = str(e)
        if "PGRST205" not in err_str and "schema cache" not in err_str:
            st.warning(f"Aviso de leitura na tabela `{table_name}`: {e}")
        return pd.DataFrame()

def normalizar_df_vendas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df_res = df.copy()

    s_tb = get_numeric_series(df_res, "tarifa_bancaria") if "tarifa_bancaria" in df_res.columns else pd.Series(0.0, index=df_res.index)
    s_tc = get_numeric_series(df_res, "tarifa_cartao") if "tarifa_cartao" in df_res.columns else pd.Series(0.0, index=df_res.index)
    s_t = get_numeric_series(df_res, "tarifa") if "tarifa" in df_res.columns else pd.Series(0.0, index=df_res.index)

    tarifa_calc = s_tb.copy()
    tarifa_calc = tarifa_calc.where(tarifa_calc > 0, s_tc)
    tarifa_calc = tarifa_calc.where(tarifa_calc > 0, s_t)
    df_res["tarifa_bancaria_calc"] = tarifa_calc.fillna(0.0)

    col_v = "valor_venda" if "valor_venda" in df_res.columns else ("valor" if "valor" in df_res.columns else "valor_total")
    df_res["valor_bruto_calc"] = get_numeric_series(df_res, col_v)

    df_res["liquido_recebido_calc"] = (df_res["valor_bruto_calc"] - df_res["tarifa_bancaria_calc"]).clip(lower=0.0)

    return df_res

def safe_insert(table_name: str, payload: dict):
    if not supabase:
        return False
    try:
        supabase.table(table_name).insert(payload).execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "PGRST205" in err_str or "custos_avulsos" in err_str or "baixas_estoque" in err_str or "devolucoes_vendas" in err_str:
            if table_name == "custos_avulsos":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["custos_avulsos_local"]) + 1000
                st.session_state["custos_avulsos_local"].append(payload_copy)
                return True
            elif table_name == "baixas_estoque":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["baixas_estoque_local"]) + 1000
                st.session_state["baixas_estoque_local"].append(payload_copy)
                return True
            elif table_name == "devolucoes_vendas":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["devolucoes_venda_local"]) + 1000
                st.session_state["devolucoes_venda_local"].append(payload_copy)
                return True
        if "Could not find the '" in err_str and "' column" in err_str:
            col_err = err_str.split("Could not find the '")[1].split("' column")[0]
            if col_err in payload:
                del payload[col_err]
                return safe_insert(table_name, payload)
        st.error(f"Erro ao gravar na tabela `{table_name}`: {err}")
        return False

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
    if not supabase or not codigo_prod or qtd_venda <= 0:
        return
    try:
        res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
        if res_p.data and len(res_p.data) > 0:
            prod_row = res_p.data[0]
            col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
            qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
            novo_estoque = max(0, qtd_atual - int(qtd_venda))
            supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
    except Exception as e:
        st.error(f"Erro ao atualizar estoque do produto: {e}")

def estornar_estoque(codigo_prod, qtd_estorno):
    if not supabase or not codigo_prod or qtd_estorno <= 0:
        return
    try:
        res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
        if res_p.data and len(res_p.data) > 0:
            prod_row = res_p.data[0]
            col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
            qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
            novo_estoque = qtd_atual + int(qtd_estorno)
            supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
    except Exception as e:
        st.error(f"Erro ao estornar produto ao estoque: {e}")

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

    # 1. Compras de Mercadorias
    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        agrup_cm = df_cm.groupby("data_str").agg(total_custo=("total_item_calc", "sum")).reset_index()
        for _, r in agrup_cm.iterrows():
            tot_c = float(r["total_custo"])
            if tot_c > 0:
                lista_movimentos.append({"Data_Val": r["data_str"], "Valor_Num": -tot_c})

    # 2. Recebimentos das Vendas
    if not df_vendas_in.empty:
        df_v_norm = normalizar_df_vendas(df_vendas_in)
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_v_norm.columns else ("data_receb" if "data_receb" in df_v_norm.columns else "data")
        for _, r in df_v_norm.iterrows():
            dt_v = r.get(col_dt_rec) or r.get("data")
            val_v_calc = float(r.get("liquido_recebido_calc", 0.0))
            if val_v_calc > 0:
                lista_movimentos.append({"Data_Val": parse_date_str(dt_v), "Valor_Num": val_v_calc})

    # 3. Custos e Despesas
    if not df_custos_in.empty:
        for _, r in df_custos_in.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            if val_c > 0:
                lista_movimentos.append({"Data_Val": parse_date_str(r.get("data")), "Valor_Num": -val_c})

    # 4. Aportes e Devoluções
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

    # 5. Devoluções de Vendas
    if not df_devolucoes_in.empty:
        for _, r in df_devolucoes_in.iterrows():
            val_dev = float(pd.to_numeric(r.get("valor_devolvido", 0.0), errors="coerce") or 0.0)
            if val_dev > 0:
                dt_dev_raw = r.get("data_devolucao")
                dt_dev_str = parse_date_str(dt_dev_raw) if dt_dev_raw else datetime.date.today().strftime("%Y-%m-%d")
                lista_movimentos.append({"Data_Val": dt_dev_str, "Valor_Num": -val_dev})

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
        ["📈 Dashboard", "📦 Pedidos", "🛍 Compra de Mercadorias", "📦 Estoque", "🛒 Vendas", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "💾 Gestão de Dados", "⚙ Configuração"],
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

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_d_venda = "data" if "data" in df_vendas.columns else ("data_venda" if "data_venda" in df_vendas.columns else None)
    meses_disponiveis = ["TODOS"]
    if not df_vendas.empty and col_d_venda:
        df_vendas["mes_ano"] = pd.to_datetime(df_vendas[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
        meses_disponiveis.extend(sorted(df_vendas["mes_ano"].dropna().unique().tolist()))
    
    mes_sel = st.selectbox("📅 Selecionar Período / Mês:", list(set(meses_disponiveis)))
    
    df_vendas_fil = df_vendas.copy()
    if mes_sel != "TODOS" and not df_vendas_fil.empty and col_d_venda:
        df_vendas_fil["mes_temp"] = pd.to_datetime(df_vendas_fil[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
        df_vendas_fil = df_vendas_fil[df_vendas_fil["mes_temp"] == mes_sel]
        
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### 🟢 Faturamento vs. 🔴 CMV")
        if not df_vendas_fil.empty and col_d_venda and col_v_val:
            df_vendas_fil["mes"] = pd.to_datetime(df_vendas_fil[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
            y_cols = [col_v_val]
            if "custo" in df_vendas_fil.columns:
                y_cols.append("custo")
            agrup = df_vendas_fil.groupby("mes")[y_cols].sum().reset_index()
            fig1 = px.bar(agrup, x="mes", y=y_cols, barmode="group",
                          color_discrete_sequence=["#10b981", "#ef4444"], template="plotly_white")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Sem dados suficientes para gerar o gráfico.")

    with g2:
        st.markdown("#### 🎨 Cores Mais Vendidas")
        c_v_col = "codigo_bone" if "codigo_bone" in df_vendas_fil.columns else ("codigo" if "codigo" in df_vendas_fil.columns else "codigo_produto")
        if not df_vendas_fil.empty and c_v_col in df_vendas_fil.columns and not df_produtos.empty:
            df_m = df_vendas_fil.merge(df_produtos, left_on=c_v_col, right_on="codigo", how="left")
            cor_col = "cor" if "cor" in df_m.columns else "cor_x"
            if cor_col in df_m.columns:
                qtd_col = "qtd_x" if "qtd_x" in df_m.columns else ("qtd" if "qtd" in df_m.columns else "qtd_y")
                agrup_cor = df_m.groupby(cor_col)[qtd_col].sum().reset_index()
                fig2 = px.pie(agrup_cor, names=cor_col, values=qtd_col, hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sem informação de cor cadastrada.")
        else:
            st.info("Nenhuma venda registrada.")

elif "Compra de Mercadorias" in menu:
    st.subheader("🛍 Relatório de Compra de Mercadorias")
    
    df_cm = get_df_compra_mercadorias()

    if df_cm.empty:
        st.info("Nenhum pedido entregue disponível para o relatório de compra de mercadorias.")
    else:
        df_cm["Mes_Ano"] = pd.to_datetime(df_cm["Data_Raw"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
        
        meses_unicos_cm = df_cm["Mes_Ano"].unique()
        for mes in sorted(meses_unicos_cm, reverse=True):
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
        opcoes_itens = ["➕ [NOVO] Cadastrar Novo Item"]
        if not df_todos_pedidos.empty:
            for _, r in df_todos_pedidos.iterrows():
                id_p = r.get("id")
                lote_p = r.get("lote_id", "")
                cor_p = r.get("cor_bone", "")
                arte_p = r.get("frase_arte", "")
                opcoes_itens.append(f"✏ [ID #{id_p}] Pedido: {lote_p} | {cor_p} - {arte_p}")

        item_ped_sel = st.selectbox(
            "📌 Selecione uma opção para Cadastrar Novo ou Editar/Excluir um Item Existente:",
            opcoes_itens,
            key="sel_man_ped_item"
        )

        dados_p_edit = {}
        is_edit_ped = False
        id_ped_edit = None

        if item_ped_sel and not item_ped_sel.startswith("➕"):
            is_edit_ped = True
            try:
                id_ped_edit = int(item_ped_sel.split("]")[0].replace("✏ [ID #", "").strip())
                match_p = df_todos_pedidos[df_todos_pedidos["id"] == id_ped_edit]
                if not match_p.empty:
                    dados_p_edit = match_p.iloc[0].to_dict()
            except Exception:
                pass

        with st.form("form_novo_pedido_manual"):
            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                lote_m = st.text_input("Identificador / Lote do Pedido *", value=str(dados_p_edit.get("lote_id", "Pedido #3.10-2026")))
                cor_b_m = st.text_input("Cor do Boné *", value=str(dados_p_edit.get("cor_bone", "")))
            with c_p2:
                arte_m = st.text_input("Arte Estampada *", value=str(dados_p_edit.get("frase_arte", "")))
                cor_e_m = st.text_input("Cor da Estampa", value=str(dados_p_edit.get("cor_linha", "")))
            with c_p3:
                prod_opts = ["Básico", "Kids", "Outro", "Premium"]
                prod_cur = str(dados_p_edit.get("tipo", "Básico"))
                idx_prod = prod_opts.index(prod_cur) if prod_cur in prod_opts else 0
                prod_m = st.selectbox("Produto *", prod_opts, index=idx_prod)
                preco_m = st.number_input("Preço Base (R$) *", min_value=0.0, value=float(dados_p_edit.get("preco", 29.0)), format="%.2f")

            c_ex1, c_ex2, c_ex3 = st.columns(3)
            with c_ex1:
                v_extra_m = st.number_input("Estampa Extra (R$)", min_value=0.0, value=float(dados_p_edit.get("valor_estampa_extra", 0.0)), format="%.2f")
            with c_ex2:
                v_matriz_m = st.number_input("Matriz Bordado (R$)", min_value=0.0, value=float(dados_p_edit.get("valor_matriz", 0.0)), format="%.2f")
            with c_ex3:
                dt_init_val = datetime.date.today()
                if is_edit_ped and dados_p_edit.get("data_criacao"):
                    try:
                        dt_init_val = pd.to_datetime(parse_date_str(dados_p_edit.get("data_criacao"))).date()
                    except Exception:
                        pass
                dt_p_m = st.date_input("Data da Criação *", dt_init_val, format="DD/MM/YYYY")

            obs_p_m = st.text_area("Observações do Pedido", value=str(dados_p_edit.get("observacoes", "")))

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                btn_cadastrar_p = st.form_submit_button("💾 Cadastrar Item", use_container_width=True, type="primary")
            with col_b2:
                btn_atualizar_p = st.form_submit_button("✏ Atualizar Item", use_container_width=True)
            with col_b3:
                btn_excluir_p = st.form_submit_button("🗑 Excluir Item", use_container_width=True)

            if btn_cadastrar_p:
                if not lote_m.strip() or not cor_b_m.strip() or not arte_m.strip():
                    st.error("Preencha os campos obrigatórios (Lote, Cor e Arte)!")
                else:
                    dt_p_str = parse_date_str(dt_p_m)
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, status, valor_estampa_extra, valor_matriz)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (lote_m.strip(), dt_p_str, cor_b_m.strip(), arte_m.strip(), cor_e_m.strip(), prod_m, preco_m, obs_p_m.strip(), "Em Produção", v_extra_m, v_matriz_m))
                    conn.commit()
                    conn.close()

                    if supabase:
                        safe_insert("pedidos", {
                            "lote_id": lote_m.strip(),
                            "data_criacao": dt_p_str,
                            "cor_bone": cor_b_m.strip(),
                            "frase_arte": arte_m.strip(),
                            "cor_linha": cor_e_m.strip(),
                            "tipo": prod_m,
                            "preco": preco_m,
                            "observacoes": obs_p_m.strip(),
                            "status": "Em Produção",
                            "valor_estampa_extra": v_extra_m,
                            "valor_matriz": v_matriz_m
                        })

                    st.session_state["flash_success"] = f"🎉 Item cadastrado no lote '{lote_m.strip()}' com sucesso!"
                    st.rerun()

            if btn_atualizar_p:
                if not is_edit_ped or not id_ped_edit:
                    st.error("Selecione um item existente para atualizar!")
                elif not lote_m.strip() or not cor_b_m.strip() or not arte_m.strip():
                    st.error("Preencha os campos obrigatórios (Lote, Cor e Arte)!")
                else:
                    dt_p_str = parse_date_str(dt_p_m)
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute('''
                        UPDATE pedidos SET lote_id=?, data_criacao=?, cor_bone=?, frase_arte=?, cor_linha=?, tipo=?, preco=?, observacoes=?, valor_estampa_extra=?, valor_matriz=?
                        WHERE id=?
                    ''', (lote_m.strip(), dt_p_str, cor_b_m.strip(), arte_m.strip(), cor_e_m.strip(), prod_m, preco_m, obs_p_m.strip(), v_extra_m, v_matriz_m, id_ped_edit))
                    conn.commit()
                    conn.close()

                    if supabase:
                        try:
                            supabase.table("pedidos").update({
                                "lote_id": lote_m.strip(),
                                "data_criacao": dt_p_str,
                                "cor_bone": cor_b_m.strip(),
                                "frase_arte": arte_m.strip(),
                                "cor_linha": cor_e_m.strip(),
                                "tipo": prod_m,
                                "preco": preco_m,
                                "observacoes": obs_p_m.strip(),
                                "valor_estampa_extra": v_extra_m,
                                "valor_matriz": v_matriz_m
                            }).eq("id", id_ped_edit).execute()
                        except Exception as err_upd:
                            st.error(f"Erro ao atualizar no Supabase: {err_upd}")

                    st.session_state["flash_success"] = f"🎉 Item ID #{id_ped_edit} atualizado com sucesso!"
                    st.rerun()

            if btn_excluir_p:
                if not is_edit_ped or not id_ped_edit:
                    st.error("Selecione um item existente para excluir!")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM pedidos WHERE id = ?", (id_ped_edit,))
                    conn.commit()
                    conn.close()

                    if supabase:
                        try:
                            supabase.table("pedidos").delete().eq("id", id_ped_edit).execute()
                        except Exception as err_del_p:
                            st.error(f"Erro ao excluir no Supabase: {err_del_p}")

                    st.session_state["flash_success"] = f"🗑️ Item ID #{id_ped_edit} excluído com sucesso!"
                    st.rerun()

    with st.expander("📥 Importar Novo Pedido via Planilha (.xlsx / .csv)", expanded=False):
        uploaded_ped_file = st.file_uploader("Carregar planilha de pedido (ex: Pedido_#3.10-2026.xlsx)", type=["xlsx", "csv"], key="uploader_pedidos_excel")
        if uploaded_ped_file is not None:
            try:
                if uploaded_ped_file.name.endswith(".csv"):
                    df_imp_ped = pd.read_csv(uploaded_ped_file, dtype=str)
                else:
                    df_imp_ped = pd.read_excel(uploaded_ped_file, dtype=str)

                nome_sugerido = uploaded_ped_file.name.rsplit(".", 1)[0].replace("_", " ")
                lote_input = st.text_input("Identificador / Lote do Pedido *", value=nome_sugerido, key="lote_imp_input")

                st.markdown("##### 🔍 Pré-visualização do Pedido a Importar:")
                st.dataframe(df_imp_ped, use_container_width=True)

                if st.button("🚀 Confirmar Importação do Pedido", type="primary", use_container_width=True):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    count_inserted = 0

                    for _, row in df_imp_ped.iterrows():
                        cor_b = str(row.get('Cor do Boné', row.get('cor_bone', ''))).strip()
                        arte = str(row.get('Arte Estampada', row.get('frase_arte', ''))).strip()
                        cor_e = str(row.get('Cor da Estampa', row.get('cor_linha', ''))).strip()
                        prod_tipo = str(row.get('Produto', row.get('tipo', 'Básico'))).strip()
                        preco_b = parse_money(row.get('Preço Base', row.get('preco', 29.0)))
                        v_extra = parse_money(row.get('Estampa Extra', row.get('valor_estampa_extra', 0.0)))
                        v_matriz = parse_money(row.get('Matriz Bordado', row.get('valor_matriz', 0.0)))
                        
                        dt_raw = str(row.get('Data', row.get('data_criacao', ''))).strip()
                        try:
                            dt_obj = pd.to_datetime(dt_raw, format="%d/%m/%Y", errors="coerce")
                            if pd.isna(dt_obj):
                                dt_obj = pd.to_datetime(dt_raw, dayfirst=True, errors="coerce")
                            dt_str = dt_obj.strftime("%Y-%m-%d") if pd.notna(dt_obj) else datetime.date.today().strftime("%Y-%m-%d")
                        except Exception:
                            dt_str = parse_date_str(dt_raw)
                        
                        st_val = str(row.get('Status', row.get('status', 'Em Produção'))).strip() or 'Em Produção'
                        obs_val = str(row.get('Observações', row.get('observacoes', ''))).strip() if pd.notna(row.get('Observações', row.get('observacoes'))) else ''

                        c.execute('''
                            INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, status, valor_estampa_extra, valor_matriz)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (lote_input.strip(), dt_str, cor_b, arte, cor_e, prod_tipo, preco_b, obs_val, st_val, v_extra, v_matriz))
                        count_inserted += 1

                        if supabase:
                            safe_insert("pedidos", {
                                "lote_id": lote_input.strip(),
                                "data_criacao": dt_str,
                                "cor_bone": cor_b,
                                "frase_arte": arte,
                                "cor_linha": cor_e,
                                "tipo": prod_tipo,
                                "preco": preco_b,
                                "observacoes": obs_val,
                                "status": st_val,
                                "valor_estampa_extra": v_extra,
                                "valor_matriz": v_matriz
                            })

                    conn.commit()
                    conn.close()

                    st.session_state["flash_success"] = f"🎉 Pedido '{lote_input.strip()}' com {count_inserted} itens importado com sucesso!"
                    st.rerun()
            except Exception as err:
                st.error(f"Erro ao importar planilha de pedido: {err}")

    st.markdown("---")

    df_ped = carregar_dataframe("SELECT id, lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, valor_estampa_extra, valor_matriz, status, observacoes, codigo_produto FROM pedidos ORDER BY id DESC")

    if df_ped.empty:
        st.info("Nenhum pedido cadastrado no momento.")
    else:
        df_ped['lote_id'] = df_ped['lote_id'].fillna('Sem Lote Definido')
        df_ped['total_item'] = df_ped['preco'] + df_ped['valor_estampa_extra'].fillna(0) + df_ped['valor_matriz'].fillna(0)
        df_ped["Mes_Ano"] = pd.to_datetime(df_ped["data_criacao"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")

        meses_pedidos = sorted(df_ped["Mes_Ano"].unique(), reverse=True)
        for mes in meses_pedidos:
            df_ped_mes = df_ped[df_ped["Mes_Ano"] == mes]
            st.markdown(f"#### 📅 Mês: {mes}")
            
            lotes_unicos = df_ped_mes['lote_id'].unique()

            for lote in lotes_unicos:
                df_lote = df_ped_mes[df_ped_mes['lote_id'] == lote].copy()
                total_qtd = len(df_lote)
                total_valor = df_lote['total_item'].sum()
                
                data_lote_raw = df_lote['data_criacao'].iloc[0] if not df_lote.empty else ""
                data_lote_fmt = format_data_br(data_lote_raw)
                
                titulo_expander = f"📅 Data: {data_lote_fmt} | 📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})" if data_lote_fmt else f"📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})"

                with st.expander(titulo_expander, expanded=False):
                    df_lote["Preço Base"] = df_lote["preco"].apply(lambda x: f"R$ {x:.2f}")
                    df_lote["Total Item"] = df_lote["total_item"].apply(lambda x: f"R$ {x:.2f}")
                    
                    cols_lote = ["cor_bone", "frase_arte"]
                    if df_lote["cor_linha"].dropna().astype(str).str.strip().ne("").any():
                        cols_lote.append("cor_linha")
                    cols_lote.append("tipo")
                    cols_lote.append("Preço Base")
                    
                    if (df_lote["valor_estampa_extra"] > 0).any():
                        df_lote["Estampa Extra"] = df_lote["valor_estampa_extra"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                        cols_lote.append("Estampa Extra")
                    if (df_lote["valor_matriz"] > 0).any():
                        df_lote["Matriz Bordado"] = df_lote["valor_matriz"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                        cols_lote.append("Matriz Bordado")
                        
                    cols_lote.append("Total Item")
                    
                    if df_lote["observacoes"].dropna().astype(str).str.strip().ne("").any():
                        cols_lote.append("observacoes")

                    df_exibicao_lote = df_lote[cols_lote].rename(columns={
                        "cor_bone": "Cor do Boné",
                        "frase_arte": "Arte Estampada",
                        "cor_linha": "Cor da Estampa",
                        "tipo": "Produto",
                        "observacoes": "Observações"
                    })
                    
                    st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)

                    st.markdown("##### 🚚 Ações do Pedido (Entregas e Acompanhamento)")
                    
                    col_e1, col_e2, col_e3, col_e4 = st.columns([3, 2, 1.5, 1.5])
                    with col_e1:
                        dict_itens_ped = {row["id"]: f"ID #{row['id']} | {row['cor_bone']} - {row['frase_arte']} (Status: {row['status']})" for _, row in df_lote.iterrows()}
                        ids_itens_acao = st.multiselect(
                            "Selecione um ou mais itens para alterar o status:", 
                            options=list(dict_itens_ped.keys()), 
                            format_func=lambda x: dict_itens_ped[x], 
                            key=f"msel_entregue_{lote}_{mes}"
                        )

                    with col_e2:
                        dt_entrega_manual = st.date_input(
                            "Data da Entrega / Aquisição *", 
                            value=datetime.date.today(), 
                            format="DD/MM/YYYY",
                            key=f"dt_entrega_{lote}_{mes}"
                        )
                    
                    with col_e3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🚚 Entregue", key=f"btn_entregue_{lote}_{mes}", use_container_width=True, type="primary"):
                            if not ids_itens_acao:
                                st.warning("Selecione ao menos um item!")
                            else:
                                codigo_base_atual = get_ultimo_codigo_config()
                                codigos_gerados = []
                                
                                conn = sqlite3.connect(DB_NAME)
                                c = conn.cursor()

                                for item_id in ids_itens_acao:
                                    row_alvo = df_lote[df_lote["id"] == item_id].iloc[0]
                                    codigo_base_atual = gerar_proximo_codigo(codigo_base_atual)
                                    codigos_gerados.append(codigo_base_atual)

                                    dt_aquisicao_item = parse_date_str(dt_entrega_manual)

                                    novo_prod = {
                                        "codigo": codigo_base_atual,
                                        "cor": str(row_alvo.get("cor_bone", "")).strip(),
                                        "frase": str(row_alvo.get("frase_arte", "")).strip(),
                                        "cor_estampa": str(row_alvo.get("cor_linha", "")).strip(),
                                        "categoria": str(row_alvo.get("tipo", "Básico")).strip(),
                                        "custo": float(row_alvo.get("preco", 29.0)),
                                        "estampa_extra": float(row_alvo.get("valor_estampa_extra", 0.0)),
                                        "matriz_bordado": float(row_alvo.get("valor_matriz", 0.0)),
                                        "qtd_estoque": 1,
                                        "qtd_comprada": 1,
                                        "data_aquisicao": dt_aquisicao_item
                                    }

                                    if safe_upsert_produto(novo_prod):
                                        c.execute("UPDATE pedidos SET status = 'Entregue / Retirado', codigo_produto = ? WHERE id = ?", (codigo_base_atual, item_id))
                                        if supabase:
                                            try:
                                                supabase.table("pedidos").update({"status": "Entregue / Retirado", "codigo_produto": codigo_base_atual}).eq("id", item_id).execute()
                                            except Exception:
                                                pass

                                conn.commit()
                                conn.close()
                                
                                set_ultimo_codigo_config(codigo_base_atual)

                                st.session_state["flash_success"] = f"🎉 {len(codigos_gerados)} item(ns) entregue(s) com sucesso em {format_data_br(dt_entrega_manual)} e cadastrado(s) no estoque (Códigos: {', '.join(codigos_gerados)})!"
                                st.rerun()

                    with col_e4:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("❌ Cancelar", key=f"btn_cancelar_{lote}_{mes}", use_container_width=True, type="secondary"):
                            if not ids_itens_acao:
                                st.warning("Selecione ao menos um item!")
                            else:
                                conn = sqlite3.connect(DB_NAME)
                                c = conn.cursor()
                                for item_id in ids_itens_acao:
                                    row_alvo = df_lote[df_lote["id"] == item_id].iloc[0]
                                    cod_prod = row_alvo.get("codigo_produto")
                                    if cod_prod and str(cod_prod).strip() != "" and str(cod_prod).strip().lower() != "none":
                                        estornar_estoque(cod_prod, 1)

                                    c.execute("DELETE FROM pedidos WHERE id = ?", (item_id,))
                                    if supabase:
                                        try:
                                            supabase.table("pedidos").delete().eq("id", item_id).execute()
                                        except Exception:
                                            pass
                                conn.commit()
                                conn.close()

                                st.session_state["flash_success"] = f"🗑 {len(ids_itens_acao)} item(ns) cancelado(s) e excluído(s) com sucesso!"
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
            
        df_est["Status"] = df_est["Estoque"].apply(lambda q: "Disponível" if q > 0 else "Esgotado")
        df_est["custo_total_num"] = df_est["preco_num"] + df_est["estampa_extra_num"] + df_est["matriz_num"]

        qtd_total_estoque = int(df_est["Estoque"].sum())
        st.markdown(f"#### 📊 **Quantidade Total em Estoque:** `{qtd_total_estoque} un`")

        with st.expander("🔻 Registrar Baixa no Estoque (Perda / Avaria / Brinde)", expanded=False):
            with st.form("form_baixa_estoque"):
                cb_c1, cb_c2, cb_c3 = st.columns(3)
                with cb_c1:
                    cods_disponiveis = df_est[df_est["Estoque"] > 0]["Código"].tolist()
                    cod_baixa = st.selectbox("Selecione a Mercadoria *", cods_disponiveis if cods_disponiveis else ["Sem itens"])
                with cb_c2:
                    motivo_baixa = st.selectbox("Motivo da Baixa *", ["Perda", "Avaria", "Brinde", "Outro"])
                    dt_baixa = st.date_input("Data da Baixa *", datetime.date.today(), format="DD/MM/YYYY")
                with cb_c3:
                    obs_baixa = st.text_input("Observação / Justificativa")
                
                btn_confirmar_baixa = st.form_submit_button("🔻 Confirmar Baixa no Estoque", type="primary", use_container_width=True)
                if btn_confirmar_baixa:
                    if cod_baixa != "Sem itens":
                        payload_baixa = {
                            "codigo": cod_baixa,
                            "motivo": motivo_baixa,
                            "observacao": obs_baixa.strip(),
                            "data_baixa": parse_date_str(dt_baixa)
                        }
                        safe_insert("baixas_estoque", payload_baixa)
                        dar_baixa_estoque_venda(cod_baixa, 1)
                        st.session_state["flash_success"] = f"🔻 Baixa do item '{cod_baixa}' por '{motivo_baixa}' realizada com sucesso!"
                        st.rerun()

        with st.expander("🔍 Consultar e Pesquisar no Estoque", expanded=True):
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                busca_texto = st.text_input("Pesquisar por Código ou Arte:")
            with c_f2:
                cat_unicas = ["Todas"] + sorted(list(df_est["Produto"].dropna().unique()))
                filtro_cat = st.selectbox("Filtrar por Produto/Categoria:", cat_unicas)
            with c_f3:
                cor_unicas = ["Todas"] + sorted(list(df_est["Cor do Boné"].dropna().unique()))
                filtro_cor = st.selectbox("Filtrar por Cor do Boné:", cor_unicas)

            df_est_filtrado = df_est.copy()
            if busca_texto:
                df_est_filtrado = df_est_filtrado[
                    df_est_filtrado["Código"].astype(str).str.contains(busca_texto, case=False, na=False) |
                    df_est_filtrado["Arte Estampada"].astype(str).str.contains(busca_texto, case=False, na=False)
                ]
            if filtro_cat != "Todas":
                df_est_filtrado = df_est_filtrado[df_est_filtrado["Produto"] == filtro_cat]
            if filtro_cor != "Todas":
                df_est_filtrado = df_est_filtrado[df_est_filtrado["Cor do Boné"] == filtro_cor]

        df_est_filtrado["Custo Base"] = df_est_filtrado["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Estampa Extra"] = df_est_filtrado["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Matriz Bordado"] = df_est_filtrado["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Custo Total"] = df_est_filtrado["custo_total_num"].apply(lambda v: f"R$ {float(v):,.2f}")

        cols_est = [
            "Status", "Código", "Cor do Boné", "Arte Estampada", "Cor da Estampa", 
            "Produto", "Estoque", "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Total"
        ]

        st.dataframe(df_est_filtrado[cols_est], use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif "Vendas" in menu:
    st.subheader("🛒 Lançar Nova Venda")
    
    df_cm_estoque = get_df_compra_mercadorias()
    map_estoque_disponivel = {}
    
    if not df_cm_estoque.empty:
        df_cm_estoque = df_cm_estoque[~df_cm_estoque["Código"].isin(CODIGOS_REMOVER)]
        
        if not df_produtos.empty and "codigo" in df_produtos.columns:
            col_q = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
            df_cm_estoque = df_cm_estoque.merge(df_produtos[["codigo", col_q]], left_on="Código", right_on="codigo", how="left")
            df_cm_estoque["qtd_disp"] = pd.to_numeric(df_cm_estoque[col_q], errors="coerce").fillna(1).astype(int)
        else:
            df_cm_estoque["qtd_disp"] = 1

        df_cm_disponivel = df_cm_estoque[df_cm_estoque["qtd_disp"] > 0]
        
        opts = []
        for _, r in df_cm_disponivel.iterrows():
            cod_item = r['Código']
            q_disp = int(r['qtd_disp'])
            map_estoque_disponivel[cod_item] = q_disp
            opts.append(f"[{cod_item}] \"{r.get('Arte Estampada','')}\" - Cor: {r.get('Cor do Boné','')} (Disponível: {q_disp} un)")
    else:
        df_cm_disponivel = pd.DataFrame()
        opts = []

    if not opts:
        st.warning("⚠️ Nenhum boné disponível em estoque para venda no momento.")
        prod_sel = None
        codigo_sel = ""
    else:
        prod_sel = st.selectbox(
            "🔍 Selecione/Pesquise o Boné no Estoque:",
            opts,
            index=0,
            help="Mostra apenas itens com estoque disponível."
        )
        codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""

    max_qtd_permitida = map_estoque_disponivel.get(codigo_sel, 1) if codigo_sel else 1

    c1, c2, c3 = st.columns(3)
    with c1:
        qtd_venda = st.number_input(
            "Quantidade *", 
            min_value=1, 
            max_value=max_qtd_permitida, 
            value=1, 
            step=1,
            help=f"Estoque limite atual: {max_qtd_permitida} un"
        )
        cliente = st.text_input("Nome do Cliente *")
    with c2:
        valor_venda = st.number_input("Valor de Venda (R$) *", min_value=0.0, value=0.0, step=5.0, format="%.2f")
        forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])
    with c3:
        data_venda = st.date_input("Data da Venda *", datetime.date.today(), format="DD/MM/YYYY")
        tarifa_bancaria = st.number_input("Tarifa Bancária (R$) (Opcional)", min_value=0.0, value=0.0, step=0.5, format="%.2f")

    data_receb = st.date_input("Data de Recebimento (Opcional)", value=None, format="DD/MM/YYYY")

    valor_recebido = max(0.0, float(valor_venda) - float(tarifa_bancaria))

    st.markdown(f"👉 **Líquido Recebido Calculado:** `R$ {valor_recebido:,.2f}`")

    if st.button("🚀 Finalizar Venda Individual", type="primary", use_container_width=True):
        if not cliente.strip():
            st.error("Informe o nome do cliente!")
        elif not codigo_sel.strip():
            st.error("Selecione um produto com estoque válido!")
        else:
            custo_total_cm = 0.0
            if not df_cm_estoque.empty and codigo_sel in df_cm_estoque["Código"].values:
                p_info = df_cm_estoque[df_cm_estoque["Código"] == codigo_sel].iloc[0]
                custo_total_cm = float(p_info.get("total_item_calc", 0.0))
            
            dt_venda_str = parse_date_str(data_venda)
            dt_receb_str = parse_date_str(data_receb) if data_receb is not None else None
            val_venda_fmt = round(float(valor_venda), 2)
            tarifa_fmt = round(float(tarifa_bancaria), 2)
            val_receb_fmt = round(max(0.0, val_venda_fmt - tarifa_fmt), 2)

            payload_venda = {
                "codigo_bone": codigo_sel.strip(),
                "codigo": codigo_sel.strip(),
                "cliente": cliente.strip(),
                "qtd": int(qtd_venda),
                "valor_venda": val_venda_fmt,
                "valor_recebido": val_receb_fmt,
                "tarifa_bancaria": tarifa_fmt,
                "tarifa_cartao": tarifa_fmt,
                "tarifa": tarifa_fmt,
                "forma_pagto": forma_pagto,
                "data": dt_venda_str,
                "data_venda": dt_venda_str,
                "custo": custo_total_cm,
                "custo_unitario": custo_total_cm
            }
            if dt_receb_str:
                payload_venda["data_recebimento"] = dt_receb_str

            if safe_insert("vendas", payload_venda):
                dar_baixa_estoque_venda(codigo_sel.strip(), int(qtd_venda))

                if dt_receb_str and val_receb_fmt > 0:
                    safe_insert("caixa", {
                        "data": dt_receb_str,
                        "desc": f"Venda {codigo_sel.strip()} ({qtd_venda}un) - {cliente.strip()}",
                        "tipo": "Venda",
                        "valor": val_receb_fmt
                    })
                    
                st.session_state["flash_success"] = f"🎉 Venda salva com sucesso! Líquido Recebido: R$ {val_receb_fmt:,.2f} (Tarifa Bancária: R$ {tarifa_fmt:,.2f})"
                st.rerun()

    st.markdown("---")
    with st.expander("📥 Importar Vendas via Planilha (.xlsx / .csv)", expanded=False):
        st.markdown("##### 📌 Modelo de Planilha de Vendas:")
        df_modelo_vendas = pd.DataFrame([{
            "Código": "BL-0005",
            "Quantidade": 1,
            "Valor": 80.00,
            "Tarifa": 3.50,
            "Data da Venda": "05/10/2026",
            "Nome do Cliente": "João Silva",
            "Forma de Pagto": "Cartão",
            "Data de Recebimento": "05/10/2026"
        }])
        st.dataframe(df_modelo_vendas, use_container_width=True, hide_index=True)
        
        output_v = io.BytesIO()
        with pd.ExcelWriter(output_v, engine='openpyxl') as writer:
            df_modelo_vendas.to_excel(writer, index=False, sheet_name="Modelo_Vendas")
        
        st.download_button(
            "📥 Baixar Modelo de Planilha de Vendas (.xlsx)",
            data=output_v.getvalue(),
            file_name="Modelo_Importacao_Vendas_R2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        uploaded_v_file = st.file_uploader("Enviar arquivo de vendas (.xlsx ou .csv)", type=["xlsx", "csv"], key="uploader_vendas_final")
        if uploaded_v_file is not None:
            try:
                df_imp_v = pd.read_csv(uploaded_v_file, dtype=str) if uploaded_v_file.name.endswith(".csv") else pd.read_excel(uploaded_v_file, dtype=str)
                st.markdown("##### 🔍 Pré-visualização das Vendas a Importar:")
                st.dataframe(df_imp_v, use_container_width=True)
                
                if st.button("🚀 Confirmar Importação de Vendas", type="primary", use_container_width=True):
                    count_v_imp = 0
                    for _, row in df_imp_v.iterrows():
                        cod_v = str(row.get('Código', row.get('codigo', ''))).strip()
                        qtd_v = int(pd.to_numeric(row.get('Quantidade', row.get('qtd', 1)), errors='coerce') or 1)
                        val_v = parse_money(row.get('Valor', row.get('valor_venda', 0.0)))
                        tar_v = parse_money(row.get('Tarifa', row.get('tarifa_bancaria', 0.0)))
                        rec_v = max(0.0, val_v - tar_v)
                        
                        dt_v_raw = row.get('Data da Venda', row.get('data', datetime.date.today()))
                        dt_v_str = parse_date_str(dt_v_raw)
                        
                        cli_v = str(row.get('Nome do Cliente', row.get('cliente', ''))).strip()
                        pag_v = str(row.get('Forma de Pagto', row.get('forma_pagto', 'PIX'))).strip()
                        dt_rec_v = row.get('Data de Recebimento', row.get('data_recebimento'))
                        dt_rec_v_str = parse_date_str(dt_rec_v) if pd.notna(dt_rec_v) and str(dt_rec_v).strip() != "" else None
                        
                        payload_imp_v = {
                            "codigo_bone": cod_v,
                            "codigo": cod_v,
                            "cliente": cli_v,
                            "qtd": qtd_v,
                            "valor_venda": val_v,
                            "tarifa_bancaria": tar_v,
                            "tarifa_cartao": tar_v,
                            "tarifa": tar_v,
                            "valor_recebido": rec_v,
                            "forma_pagto": pag_v,
                            "data": dt_v_str,
                            "data_venda": dt_v_str,
                            "custo": val_v,
                            "custo_unitario": val_v
                        }
                        if dt_rec_v_str:
                            payload_imp_v["data_recebimento"] = dt_rec_v_str

                        safe_insert("vendas", payload_imp_v)
                        dar_baixa_estoque_venda(cod_v, qtd_v)
                        count_v_imp += 1

                    st.session_state["flash_success"] = f"🎉 {count_v_imp} vendas importadas com sucesso!"
                    st.rerun()
            except Exception as ex_v:
                st.error(f"Erro ao processar planilha de vendas: {ex_v}")

elif "Custos" in menu:
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷 Custos de Venda", "🎪 Feiras", "💳 Custos Financeiros"], horizontal=True)

    if "Mercadorias" in sub_tab:
        df_cm = get_df_compra_mercadorias()

        if not df_cm.empty:
            df_m = df_cm.copy()
            df_m["qtd_num"] = 1
            df_m["Mes_Ano"] = pd.to_datetime(df_m["Data_Raw"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")

            meses_custos_m = sorted(df_m["Mes_Ano"].unique(), reverse=True)
            for mes in meses_custos_m:
                df_m_mes = df_m[df_m["Mes_Ano"] == mes]
                st.markdown(f"#### 📅 Mês: {mes}")

                agrup_data = df_m_mes.groupby("Data").agg({
                    "qtd_num": "sum",
                    "total_item_calc": "sum"
                }).reset_index().rename(columns={"Data": "Data da Aquisição", "qtd_num": "Quantidade Comprada"})

                agrup_data["Custo Total"] = agrup_data["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                st.dataframe(agrup_data[["Data da Aquisição", "Quantidade Comprada", "Custo Total"]], use_container_width=True, hide_index=True)

                with st.expander("🔍 Visualizar Registros Individuais de Compras", expanded=False):
                    df_m_mes["Custo Base"] = df_m_mes["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                    df_m_mes["Estampa Extra"] = df_m_mes["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                    df_m_mes["Matriz Bordado"] = df_m_mes["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                    df_m_mes["Custo Unit. Total"] = df_m_mes["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                    df_m_mes["Custo Total"] = df_m_mes["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                    
                    cols_ind = ["Código", "Produto", "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Unit. Total", "Custo Total", "Data"]
                    st.dataframe(df_m_mes[cols_ind], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma aquisição de mercadoria registrada no momento.")

    elif "Venda" in sub_tab:
        with st.form("form_cv"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cv = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
                desc_cv = st.text_input("Descrição *")
            with c2:
                tipo_cv = st.selectbox("Tipo de Despesa *", ["Brindes", "Embalagem", "Unboxing"])
            with c3:
                val_cv = st.number_input("Valor (R$) *", min_value=0.01, value=10.0, format="%.2f")

            if st.form_submit_button("Adicionar Custo de Venda", use_container_width=True):
                val_cv_fmt = round(float(val_cv), 2)
                dt_cv_str = parse_date_str(dt_cv)
                
                payload_cv = {
                    "subcategoria": "Custos de Venda",
                    "data": dt_cv_str,
                    "desc": desc_cv.strip(),
                    "tipo": tipo_cv,
                    "valor": val_cv_fmt
                }
                
                if safe_insert("custos_avulsos", payload_cv):
                    safe_insert("caixa", {
                        "data": dt_cv_str, 
                        "desc": f"[Custos de Venda] {desc_cv.strip()}", 
                        "tipo": tipo_cv, 
                        "valor": val_cv_fmt
                    })
                    st.session_state["flash_success"] = "Custo de Venda registrado com sucesso!"
                    st.rerun()

        st.markdown("---")
        st.markdown("##### 📋 Demonstrativo de Custos de Venda Lançados")
        
        if not df_custos.empty:
            subcat_col = df_custos.get("subcategoria", pd.Series([""] * len(df_custos))).fillna("").astype(str)
            df_cv_exib = df_custos[subcat_col.str.contains("venda", case=False, na=False)].copy()
            
            if not df_cv_exib.empty:
                df_cv_exib["Mes_Ano"] = pd.to_datetime(df_cv_exib["data"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
                meses_cv = sorted(df_cv_exib["Mes_Ano"].unique(), reverse=True)
                
                for mes in meses_cv:
                    df_cv_mes = df_cv_exib[df_cv_exib["Mes_Ano"] == mes]
                    st.markdown(f"#### 📅 Mês: {mes}")
                    
                    for idx, row in df_cv_mes.iterrows():
                        c_id = row.get("id")
                        c_dt = format_data_br(row.get("data"))
                        c_tp = row.get("tipo", "")
                        c_desc = row.get("desc") or row.get("descricao") or ""
                        c_vl = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)

                        col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                        with col1:
                            st.write(f"**Data:** {c_dt}")
                        with col2:
                            st.write(f"**Tipo:** {c_tp}")
                        with col3:
                            st.write(f"**Descrição:** {c_desc}")
                        with col4:
                            st.write(f"**Valor:** R$ {c_vl:,.2f}")
                        with col5:
                            if st.button("🗑 Excluir", key=f"del_cv_{c_id}_{mes}", use_container_width=True):
                                if supabase:
                                    try:
                                        supabase.table("custos_avulsos").delete().eq("id", c_id).execute()
                                    except Exception:
                                        pass
                                st.session_state["custos_avulsos_local"] = [item for item in st.session_state["custos_avulsos_local"] if item.get("id") != c_id]
                                st.session_state["flash_success"] = "Custo de venda excluído!"
                                st.rerun()
                        st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Nenhum custo de venda registrado até o momento.")
        else:
            st.info("Nenhum custo registrado.")

    elif "Feiras" in sub_tab:
        with st.form("form_cf"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cf = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
                feira_cf = st.text_input("Nome da Feira *")
            with c2:
                desc_cf = st.text_input("Descrição *")
                tipo_cf = st.selectbox("Tipo de Despesa *", ["Alimentação", "Decoração", "Instalação", "Taxa de Inscrição", "Transporte"])
            with c3:
                val_cf = st.number_input("Valor (R$) *", min_value=0.01, value=50.0, format="%.2f")

            if st.form_submit_button("Adicionar Custo de Feira", use_container_width=True):
                val_cf_fmt = round(float(val_cf), 2)
                dt_cf_str = parse_date_str(dt_cf)
                
                payload_cf = {
                    "subcategoria": "Feiras",
                    "data": dt_cf_str,
                    "desc": f"Feira: {feira_cf.strip()} - {desc_cf.strip()}",
                    "tipo": tipo_cf,
                    "valor": val_cf_fmt
                }
                
                if safe_insert("custos_avulsos", payload_cf):
                    safe_insert("caixa", {
                        "data": dt_cf_str, 
                        "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}", 
                        "tipo": tipo_cf, 
                        "valor": val_cf_fmt
                    })
                    st.session_state["flash_success"] = "Custo de Feira registrado com sucesso!"
                    st.rerun()

        st.markdown("---")
        st.markdown("##### 📋 Demonstrativo de Custos de Feiras Lançados")
        
        if not df_custos.empty:
            subcat_col = df_custos.get("subcategoria", pd.Series([""] * len(df_custos))).fillna("").astype(str)
            df_cf_exib = df_custos[subcat_col.str.contains("feira", case=False, na=False)].copy()
            
            if not df_cf_exib.empty:
                df_cf_exib["Mes_Ano"] = pd.to_datetime(df_cf_exib["data"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
                meses_cf = sorted(df_cf_exib["Mes_Ano"].unique(), reverse=True)
                
                for mes in meses_cf:
                    df_cf_mes = df_cf_exib[df_cf_exib["Mes_Ano"] == mes]
                    st.markdown(f"#### 📅 Mês: {mes}")
                    
                    for idx, row in df_cf_mes.iterrows():
                        f_id = row.get("id")
                        f_dt = format_data_br(row.get("data"))
                        f_tp = row.get("tipo", "")
                        f_desc = row.get("desc") or row.get("descricao") or ""
                        f_vl = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)

                        col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                        with col1:
                            st.write(f"**Data:** {f_dt}")
                        with col2:
                            st.write(f"**Tipo:** {f_tp}")
                        with col3:
                            st.write(f"**Descrição:** {f_desc}")
                        with col4:
                            st.write(f"**Valor:** R$ {f_vl:,.2f}")
                        with col5:
                            if st.button("🗑 Excluir", key=f"del_cf_{f_id}_{mes}", use_container_width=True):
                                if supabase:
                                    try:
                                        supabase.table("custos_avulsos").delete().eq("id", f_id).execute()
                                    except Exception:
                                        pass
                                st.session_state["custos_avulsos_local"] = [item for item in st.session_state["custos_avulsos_local"] if item.get("id") != f_id]
                                st.session_state["flash_success"] = "Custo de feira excluído!"
                                st.rerun()
                        st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Nenhum custo de feira registrado até o momento.")
        else:
            st.info("Nenhum custo registrado.")

    elif "Financeiros" in sub_tab:
        st.markdown("##### 💳 Demonstrativo de Tarifas de Cartão")
        if not df_vendas.empty:
            df_v_fin = normalizar_df_vendas(df_vendas)
            col_d_v = "data_venda" if "data_venda" in df_v_fin.columns else "data"
            col_c_b = "codigo_bone" if "codigo_bone" in df_v_fin.columns else "codigo"
            col_cli = "cliente" if "cliente" in df_v_fin.columns else "nome_cliente"

            df_v_tarifa = df_v_fin[
                (df_v_fin["tarifa_bancaria_calc"] > 0) | 
                (df_v_fin.get("forma_pagto", pd.Series([""] * len(df_v_fin))).astype(str).str.lower().str.contains("cart", na=False))
            ].copy()

            if not df_v_tarifa.empty:
                df_v_tarifa["Data"] = df_v_tarifa[col_d_v].apply(format_data_br)
                df_v_tarifa["Código"] = df_v_tarifa.get(col_c_b, "")
                df_v_tarifa["Cliente"] = df_v_tarifa.get(col_cli, "")
                df_v_tarifa["Valor Bruto (R$)"] = df_v_tarifa["valor_bruto_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_v_tarifa["Tarifa (R$)"] = df_v_tarifa["tarifa_bancaria_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_v_tarifa["Líquido (R$)"] = df_v_tarifa["liquido_recebido_calc"].apply(lambda v: f"R$ {float(v):,.2f}")

                cols_fin = ["Data", "Código", "Cliente", "Valor Bruto (R$)", "Tarifa (R$)", "Líquido (R$)"]
                st.dataframe(df_v_tarifa[cols_fin], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma venda realizada por cartão com tarifa registrada.")
        else:
            st.info("Nenhuma tarifa registrada no sistema.")

elif "Caixa" in menu or "Fluxo" in menu:
    st.subheader("💰 Extrato Consolidado de Fluxo de Caixa")
    
    lista_movimentos = []

    # 1. Compras do Módulo Compra de Mercadorias
    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        
        agrup_cm = df_cm.groupby("data_str").agg(
            total_custo=("total_item_calc", "sum"),
            total_qtd=("id", "count")
        ).reset_index()
        
        for _, r in agrup_cm.iterrows():
            dt_c = r["data_str"]
            tot_c = float(r["total_custo"])
            tot_qtd = int(r["total_qtd"])
            if tot_c > 0:
                lista_movimentos.append({
                    "Data_Val": dt_c,
                    "Data": format_data_br(dt_c),
                    "Origem": "🛍 Compra de Mercadorias",
                    "Descrição": f"Compra Agrupada ({tot_qtd} itens adquiridos)",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -tot_c
                })

    # 2. Recebimentos das Vendas
    if not df_vendas.empty:
        df_v_norm = normalizar_df_vendas(df_vendas)
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_v_norm.columns else ("data_receb" if "data_receb" in df_v_norm.columns else "data")
        for _, r in df_v_norm.iterrows():
            dt_v = r.get(col_dt_rec) or r.get("data")
            val_v_calc = float(r.get("liquido_recebido_calc", 0.0))

            cli = r.get("cliente") or r.get("nome_cliente") or ""
            cod = r.get("codigo_bone") or r.get("codigo") or ""
            if val_v_calc > 0:
                dt_v_str = parse_date_str(dt_v)
                lista_movimentos.append({
                    "Data_Val": dt_v_str,
                    "Data": format_data_br(dt_v_str),
                    "Origem": "🛒 Recebimento de Vendas",
                    "Descrição": f"Venda {cod} - Cliente: {cli}",
                    "Tipo": "Entrada 🟢",
                    "Valor_Num": val_v_calc
                })

    # 3. Custos de Venda e Custos das Feiras
    if not df_custos.empty:
        for _, r in df_custos.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            sub_c = str(r.get("subcategoria", "Custos"))
            desc_c = r.get("desc") or r.get("descricao") or "Despesa Avulsa"
            origem_tag = "🏷️ Custos de Venda" if "venda" in sub_c.lower() else ("🎪 Custos de Feiras" if "feira" in sub_c.lower() else f"💵 Custos ({sub_c})")
            if val_c > 0:
                dt_c_str = parse_date_str(r.get("data"))
                lista_movimentos.append({
                    "Data_Val": dt_c_str,
                    "Data": format_data_br(dt_c_str),
                    "Origem": origem_tag,
                    "Descrição": desc_c,
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -val_c
                })

    # 4. Aporte e Devoluções de Sócios
    if not df_aportes.empty:
        for _, r in df_aportes.iterrows():
            val_ap = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            tipo_ap = str(r.get("tipo", ""))
            socio = r.get("socio", "")
            
            dt_ap_raw = r.get("data") or r.get("data_aporte") or r.get("created_at")
            dt_ap_str = parse_date_str(dt_ap_raw) if dt_ap_raw else datetime.date.today().strftime("%Y-%m-%d")
            
            if val_ap != 0:
                is_devolucao = "devoluc" in tipo_ap.lower() or val_ap < 0
                nome_op = "Devolução" if is_devolucao else "Aporte"
                
                lista_movimentos.append({
                    "Data_Val": dt_ap_str,
                    "Data": format_data_br(dt_ap_str),
                    "Origem": "🤝 Aporte dos Sócios",
                    "Descrição": f"{nome_op} ({socio})",
                    "Tipo": "Saída 🔴" if is_devolucao else "Entrada 🟢",
                    "Valor_Num": -abs(val_ap) if is_devolucao else abs(val_ap)
                })

    # 5. Devoluções de Vendas como Saída
    if not df_devolucoes.empty:
        for _, r in df_devolucoes.iterrows():
            val_dev = float(pd.to_numeric(r.get("valor_devolvido", 0.0), errors="coerce") or 0.0)
            cod_dev = r.get("codigo", "")
            cli_dev = r.get("cliente", "")
            dt_dev_raw = r.get("data_devolucao")
            dt_dev_str = parse_date_str(dt_dev_raw) if dt_dev_raw else datetime.date.today().strftime("%Y-%m-%d")
            if val_dev > 0:
                lista_movimentos.append({
                    "Data_Val": dt_dev_str,
                    "Data": format_data_br(dt_dev_str),
                    "Origem": "🔄 Devolução de Venda",
                    "Descrição": f"Devolução Venda {cod_dev} - Cliente: {cli_dev}",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -val_dev
                })

    if lista_movimentos:
        df_extrato = pd.DataFrame(lista_movimentos)
        
        df_extrato["Data_Raw"] = pd.to_datetime(df_extrato["Data_Val"].apply(parse_date_str), errors="coerce")
        df_extrato["Data_Raw"] = df_extrato["Data_Raw"].fillna(pd.Timestamp.now())
        df_extrato["Mes_Ano"] = df_extrato["Data_Raw"].dt.strftime("%Y-%m").fillna("Outros")
        
        df_extrato = df_extrato.sort_values(by="Data_Raw", ascending=True).reset_index(drop=True)
        
        df_extrato["Saldo_Acumulado"] = df_extrato["Valor_Num"].cumsum()
        df_extrato["Valor (R$)"] = df_extrato["Valor_Num"].apply(lambda v: f"R$ {v:,.2f}")
        df_extrato["Saldo Acumulado (R$)"] = df_extrato["Saldo_Acumulado"].apply(lambda v: f"R$ {v:,.2f}")

        meses_caixa = sorted(df_extrato["Mes_Ano"].unique(), reverse=True)
        for mes in meses_caixa:
            df_cx_mes = df_extrato[df_extrato["Mes_Ano"] == mes].copy()
            st.markdown(f"#### 📅 Mês: {mes}")
            
            cols_final = ["Data", "Origem", "Descrição", "Tipo", "Valor (R$)", "Saldo Acumulado (R$)"]
            
            saldo_final_mes = df_cx_mes["Saldo_Acumulado"].iloc[-1]
            row_saldo_final = pd.DataFrame([{
                "Data": "—",
                "Origem": "🏁 SALDO FINAL",
                "Descrição": f"Saldo Acumulado Final do Período ({mes})",
                "Tipo": "Saldo 💵",
                "Valor (R$)": f"R$ {saldo_final_mes:,.2f}",
                "Saldo Acumulado (R$)": f"R$ {saldo_final_mes:,.2f}"
            }])
            
            df_cx_mes_exib = pd.concat([df_cx_mes[cols_final], row_saldo_final], ignore_index=True)
            st.dataframe(df_cx_mes_exib, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada no fluxo de caixa.")

elif "Aportes" in menu:
    st.subheader("🤝 Registro de Aportes e Devoluções")
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_ap = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
    with c2:
        socio_ap = st.selectbox("Sócio *", ["", "Renan", "Ronald"], index=0)
    with c3:
        val_ap = st.number_input("Valor (R$) *", min_value=0.0, value=0.0, format="%.2f")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🤝 Registrar Aporte", use_container_width=True, type="primary"):
            if not socio_ap:
                st.error("Selecione o Sócio antes de continuar!")
            elif val_ap <= 0:
                st.error("Informe um valor positivo para o Aporte!")
            else:
                val_ap_fmt = round(float(val_ap), 2)
                dt_ap_str = parse_date_str(dt_ap)
                payload_ap = {
                    "data": dt_ap_str,
                    "data_aporte": dt_ap_str,
                    "socio": socio_ap,
                    "valor": val_ap_fmt,
                    "tipo": "Aporte"
                }
                if safe_insert("aportes", payload_ap):
                    safe_insert("caixa", {
                        "data": dt_ap_str,
                        "desc": f"Aporte ({socio_ap})",
                        "tipo": "Aporte de Sócio",
                        "valor": val_ap_fmt
                    })
                    st.session_state["flash_success"] = f"Aporte de R$ {val_ap_fmt:,.2f} registrado com sucesso!"
                    st.rerun()

    with col_btn2:
        if st.button("🔄 Devolução de Aporte", use_container_width=True):
            if not socio_ap:
                st.error("Selecione o Sócio antes de continuar!")
            elif val_ap <= 0:
                st.error("Informe um valor positivo para a Devolução!")
            else:
                val_ap_fmt = round(float(val_ap), 2)
                dt_ap_str = parse_date_str(dt_ap)
                payload_dev = {
                    "data": dt_ap_str,
                    "data_aporte": dt_ap_str,
                    "socio": socio_ap,
                    "valor": -val_ap_fmt,
                    "tipo": "Devolução"
                }
                if safe_insert("aportes", payload_dev):
                    safe_insert("caixa", {
                        "data": dt_ap_str,
                        "desc": f"Devolução ({socio_ap})",
                        "tipo": "Devolução de Aporte",
                        "valor": -val_ap_fmt
                    })
                    st.session_state["flash_success"] = f"Devolução de R$ {val_ap_fmt:,.2f} registrada com sucesso!"
                    st.rerun()

    st.markdown("---")
    st.subheader("📊 Resumo Consolidado por Sócio")
    
    if not df_aportes.empty:
        df_ap_calc = df_aportes.copy()
        
        if "tipo" not in df_ap_calc.columns:
            if "operacao" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["operacao"]
            elif "forma" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["forma"]
            else:
                df_ap_calc["tipo"] = "Aporte"
                
        if "socio" not in df_ap_calc.columns:
            df_ap_calc["socio"] = "Não informado"

        df_ap_calc["valor_num"] = get_numeric_series(df_ap_calc, "valor")
        
        resumo_socios = []
        for s in ["Renan", "Ronald"]:
            df_s = df_ap_calc[df_ap_calc["socio"].astype(str).str.lower() == s.lower()]
            
            ent = df_s[df_s["valor_num"] > 0]["valor_num"].sum()
            sai = abs(df_s[df_s["valor_num"] < 0]["valor_num"].sum())
            
            saldo_dev = ent - sai
            
            resumo_socios.append({
                "Sócio": s,
                "Total Aportado (R$)": f"R$ {ent:,.2f}",
                "Total Devolvido (R$)": f"R$ {sai:,.2f}",
                "Saldo a Devolver (R$)": f"R$ {saldo_dev:,.2f}"
            })
            
        st.dataframe(pd.DataFrame(resumo_socios), use_container_width=True, hide_index=True)

        st.markdown("##### 📋 Relatório Detalhado de Movimentações de Aportes")
        
        if "editing_aporte_id" not in st.session_state:
            st.session_state["editing_aporte_id"] = None

        col_dt_ap = "data" if "data" in df_aportes.columns else ("data_aporte" if "data_aporte" in df_aportes.columns else ("created_at" if "created_at" in df_aportes.columns else None))
        
        if col_dt_ap and not df_aportes.empty:
            df_aportes["Mes_Ano"] = pd.to_datetime(df_aportes[col_dt_ap].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
            
            meses_aportes = sorted(df_aportes["Mes_Ano"].unique(), reverse=True)
            for mes in meses_aportes:
                df_ap_mes = df_aportes[df_aportes["Mes_Ano"] == mes]
                st.markdown(f"#### 📅 Mês: {mes}")

                for idx, row in df_ap_mes.iterrows():
                    ap_id = row.get("id")
                    ap_dt = format_data_br(row.get(col_dt_ap))
                    ap_socio = row.get("socio", "")
                    
                    ap_val = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)
                    
                    tipo_raw = str(row.get("tipo", ""))
                    if "devoluc" in tipo_raw.lower() or ap_val < 0:
                        ap_tipo_exib = "Devolução"
                    else:
                        ap_tipo_exib = "Aporte"

                    c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 1, 1])
                    with c1:
                        st.write(f"**Data:** {ap_dt}")
                    with c2:
                        st.write(f"**Sócio:** {ap_socio}")
                    with c3:
                        st.write(f"**Operação:** {ap_tipo_exib}")
                    with c4:
                        st.write(f"**Valor:** R$ {abs(ap_val):,.2f}")
                    with c5:
                        if st.button("✏️", key=f"edit_ap_{ap_id}_{mes}", use_container_width=True):
                            st.session_state["editing_aporte_id"] = ap_id
                            st.rerun()
                    with c6:
                        if st.button("🗑", key=f"del_ap_{ap_id}_{mes}", use_container_width=True):
                            if supabase:
                                supabase.table("aportes").delete().eq("id", ap_id).execute()
                            st.session_state["flash_success"] = f"Registro ID #{ap_id} excluído com sucesso!"
                            st.rerun()

                    if st.session_state.get("editing_aporte_id") == ap_id:
                        with st.form(key=f"form_edit_ap_{ap_id}_{mes}"):
                            st.markdown(f"##### ✏ Editar Registro ID #{ap_id}")
                            e_col1, e_col2, e_col3 = st.columns(3)
                            with e_col1:
                                idx_s = 0 if ap_socio == "Renan" else 1
                                novo_socio = st.selectbox("Sócio", ["Renan", "Ronald"], index=idx_s)
                            with e_col2:
                                idx_t = 0 if ap_tipo_exib == "Aporte" else 1
                                novo_tipo = st.selectbox("Tipo", ["Aporte", "Devolução"], index=idx_t)
                            with e_col3:
                                novo_val = st.number_input("Valor (R$)", min_value=1.0, value=abs(ap_val), format="%.2f")

                            btn_s_ap, btn_c_ap = st.columns(2)
                            with btn_s_ap:
                                if st.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary"):
                                    val_final = float(novo_val) if novo_tipo == "Aporte" else -float(novo_val)
                                    if supabase:
                                        supabase.table("aportes").update({
                                            "socio": novo_socio,
                                            "tipo": novo_tipo,
                                            "valor": val_final
                                        }).eq("id", ap_id).execute()
                                    st.session_state["editing_aporte_id"] = None
                                    st.session_state["flash_success"] = "Registro atualizado com sucesso!"
                                    st.rerun()
                            with btn_c_ap:
                                if st.form_submit_button("❌ Cancelar", use_container_width=True):
                                    st.session_state["editing_aporte_id"] = None
                                    st.rerun()
                    st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
        else:
            st.info("Nenhum aporte registrado com data válida até o momento.")
    else:
        st.info("Nenhum aporte ou devolução registrado no momento.")

elif "Gestão" in menu or "Dados" in menu:
    st.subheader("💾 Gestão de Dados & Backup")
    st.markdown("Gerencie o banco de dados, faça downloads de segurança e restaure backups do sistema.")

    col_status, col_export = st.columns(2)

    with col_status:
        st.markdown("#### 📌 Status da Conexão")
        if supabase is not None:
            try:
                supabase.table("produtos").select("id").limit(1).execute()
                st.success("🟢 Conectado ao Supabase (PostgreSQL Nuvem)")
                st.caption("Seus dados estão gravados na nuvem e imunes a reinícios do servidor.")
            except Exception as e:
                st.error("🔴 Falha ao conectar com o Supabase")
                st.caption(f"Erro na verificação: {e}")
        else:
            st.error("🔴 Supabase não configurado ou credenciais inválidas")
            st.caption("Verifique as chaves SUPABASE_URL e SUPABASE_KEY em seus secrets.")

    with col_export:
        st.markdown("#### 📥 Exportar Backup Geral em Excel")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_produtos.to_excel(writer, sheet_name='Produtos_Estoque', index=False)
            df_vendas.to_excel(writer, sheet_name='Vendas', index=False)
            df_caixa.to_excel(writer, sheet_name='Caixa', index=False)
            df_aportes.to_excel(writer, sheet_name='Aportes', index=False)
            df_custos.to_excel(writer, sheet_name='Custos_Avulsos', index=False)
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Baixar Backup Geral (.xlsx)",
            data=excel_data,
            file_name=f"Backup_Geral_R2_Bones_{datetime.date.today().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("#### ⚙ Operações de Banco Supabase")
    st.info("Seu banco de dados está sincronizado diretamente na nuvem do Supabase. Todos os cadastros e edições são mantidos permanentemente.")

    with st.expander("🔄 Restaurar / Recuperar Dados via Backup Planilha (.xlsx)"):
        st.warning("⚠️ O envio de uma planilha de restauração substituirá ou atualizará os registros existentes correspondentes aos códigos e IDs.")
        uploaded_backup = st.file_uploader("Carregar Arquivo de Backup para Restauração (.xlsx)", type=["xlsx"])
        
        if uploaded_backup is not None:
            if st.button("🚀 Confirmar Restauração do Banco de Dados", type="primary", use_container_width=True):
                try:
                    xls = pd.ExcelFile(uploaded_backup)
                    
                    if "Produtos_Estoque" in xls.sheet_names and supabase:
                        df_p_rec = pd.read_excel(xls, sheet_name="Produtos_Estoque")
                        if not df_p_rec.empty:
                            supabase.table("produtos").upsert(df_p_rec.to_dict(orient="records"), on_conflict="codigo").execute()
                    
                    if "Vendas" in xls.sheet_names and supabase:
                        df_v_rec = pd.read_excel(xls, sheet_name="Vendas")
                        if not df_v_rec.empty:
                            supabase.table("vendas").upsert(df_v_rec.to_dict(orient="records")).execute()
                            
                    st.success("🎉 Dados restaurados com sucesso a partir do arquivo de backup!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro durante a restauração do backup: {ex}")

elif "Configuração" in menu or "Configuracao" in menu:
    st.subheader("⚙️ Configurações Gerais do Sistema")
    st.markdown("Gerencie variáveis de sistema, sequenciais de código e parâmetros operacionais.")

    ult_cod = get_ultimo_codigo_config()

    st.markdown("#### 🏷 Sequencial do Código do Boné")
    st.info("Esta configuração determina qual foi o último código de boné registrado e serve de base para a criação automática de novos códigos quando um pedido for marcado como **Entregue**.")

    c_cfg1, c_cfg2 = st.columns(2)
    with c_cfg1:
        novo_cod_input = st.text_input(
            "Último Item Cadastrado no Estoque *", 
            value=ult_cod, 
            help="Campo alfanumérico com o formato do último produto (exemplo: BL-0001)"
        )
    
    with c_cfg2:
        prox_sugerido = gerar_proximo_codigo(novo_cod_input.strip())
        st.markdown("<br>", unsafe_allow_html=True)
        st.write(f"👉 **Próximo Código Gerado Automaticamente:** `{prox_sugerido}`")

    if st.button("💾 Salvar Parâmetros de Configuração", type="primary", use_container_width=True):
        if not novo_cod_input.strip():
            st.error("Informe um código alfanumérico válido!")
        else:
            set_ultimo_codigo_config(novo_cod_input.strip())
            st.session_state["flash_success"] = f"🎉 Configuração atualizada! O 'Último Item Cadastrado no Estoque' é '{novo_cod_input.strip()}'."
            st.rerun()
