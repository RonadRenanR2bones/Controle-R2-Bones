import datetime
import base64
import io
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
        max-height: 120px !important;
        object-fit: cover !important;
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

# Cache em sessão para guardar despesas extras (estampa extra e matriz) por código
if "extra_costs_cache" not in st.session_state:
    st.session_state["extra_costs_cache"] = {}

# Cache em sessão para gravações locais de custos avulsos quando a tabela não existir no Supabase
if "custos_avulsos_local" not in st.session_state:
    st.session_state["custos_avulsos_local"] = []

# Função auxiliar para formatar datas no padrão brasileiro DD/MM/AAAA
def format_data_br(val):
    if not val or pd.isna(val) or str(val).strip().lower() in ["none", "nat", "nan", ""]:
        return ""
    try:
        dt = pd.to_datetime(val)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(val)

# Extração segura de Séries numéricas
def get_numeric_series(df: pd.DataFrame, col_name: str, default_value: float = 0.0) -> pd.Series:
    if df.empty or col_name not in df.columns:
        return pd.Series([default_value] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col_name], errors="coerce").fillna(default_value)

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

def safe_insert(table_name: str, payload: dict):
    if not supabase:
        return False
    try:
        supabase.table(table_name).insert(payload).execute()
        return True
    except Exception as err:
        err_str = str(err)
        # Se a tabela custos_avulsos não existir no schema do Supabase, guarda fallback em memória/caixa
        if "PGRST205" in err_str or "custos_avulsos" in err_str:
            if table_name == "custos_avulsos":
                payload_copy = payload.copy()
                payload_copy["id"] = len(st.session_state["custos_avulsos_local"]) + 1000
                st.session_state["custos_avulsos_local"].append(payload_copy)
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

# Carregar tabelas
df_produtos = fetch_data("produtos")
df_vendas = fetch_data("vendas")
df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")

# Mescla custos_avulsos do banco com salvamento local se houver
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
        ["📈 Dashboard", "🛍️️ Compras", "📦 Estoque", "🛒 Vendas", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "📥 Importação", "💾 Gestão de Dados"],
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

# 5. Módulos

if menu == "📈 Dashboard":
    st.subheader("📈 Dashboard Executivo")
    
    col_v_val = "valor_venda" if "valor_venda" in df_vendas.columns else ("valor" if "valor" in df_vendas.columns else ("valor_total" if "valor_total" in df_vendas.columns else None))
    total_faturado = float(df_vendas[col_v_val].sum()) if not df_vendas.empty and col_v_val else 0.0
    
    total_cmv = 0.0
    if not df_vendas.empty:
        if "custo" in df_vendas.columns:
            total_cmv = float(get_numeric_series(df_vendas, "custo").sum())
        elif "custo_unitario" in df_vendas.columns:
            col_q = "qtd" if "qtd" in df_vendas.columns else ("quantidade" if "quantidade" in df_vendas.columns else None)
            qtds = get_numeric_series(df_vendas, col_q, 1.0) if col_q else 1.0
            custos = get_numeric_series(df_vendas, "custo_unitario")
            total_cmv = float((custos * qtds).sum())

    saldo_caixa = 0.0
    if not df_caixa.empty and "valor" in df_caixa.columns and "tipo" in df_caixa.columns:
        df_caixa["valor_num"] = get_numeric_series(df_caixa, "valor")
        entradas = df_caixa[df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor_num"].sum()
        saidas = df_caixa[~df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor_num"].sum()
        saldo_caixa = float(entradas - saidas)

    total_qtd_vendida = 0
    if not df_vendas.empty:
        col_q_venda = "qtd" if "qtd" in df_vendas.columns else ("quantidade" if "quantidade" in df_vendas.columns else None)
        if col_q_venda:
            total_qtd_vendida = int(get_numeric_series(df_vendas, col_q_venda).sum())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV TOTAL <span class="tooltip-icon" title="Custo das mercadorias vendidas referente aos itens faturados">ℹ</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo financeiro líquido acumulado">ℹ</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Quantidade Vendida <span class="tooltip-icon" title="Quantidade total de peças/bonés faturados nas vendas">ℹ</span></div><div class="kpi-value">{total_qtd_vendida} un</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_d_venda = "data" if "data" in df_vendas.columns else ("data_venda" if "data_venda" in df_vendas.columns else None)
    meses_disponiveis = ["TODOS"]
    if not df_vendas.empty and col_d_venda:
        df_vendas["mes_ano"] = df_vendas[col_d_venda].astype(str).str.slice(0, 7)
        meses_disponiveis.extend(sorted(df_vendas["mes_ano"].unique().tolist()))
    
    mes_sel = st.selectbox("📅 Selecionar Período / Mês:", list(set(meses_disponiveis)))
    
    df_vendas_fil = df_vendas.copy()
    if mes_sel != "TODOS" and not df_vendas_fil.empty and col_d_venda:
        df_vendas_fil = df_vendas_fil[df_vendas_fil[col_d_venda].astype(str).str.startswith(mes_sel)]
        
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### 🟢 Faturamento vs. 🔴 CMV")
        if not df_vendas_fil.empty and col_d_venda and col_v_val:
            df_vendas_fil["mes"] = df_vendas_fil[col_d_venda].astype(str).str.slice(0, 7)
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

elif menu in ["🛍️ Compras", "🛍 Compras"]:
    st.subheader("🛍️ Cadastrar Nova Compra de Mercadoria")
    
    opcoes_prod = ["➕ [NOVO] Cadastrar Novo Produto"]
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        for _, r in df_produtos.iterrows():
            cod = r.get('codigo', '')
            frase = r.get('frase', '')
            cor = r.get('cor', '')
            cor_e = r.get('cor_estampa', '')
            cat = r.get('categoria', '')
            opcoes_prod.append(f"✏ [{cod}] | {frase} - {cor} - {cor_e} - {cat}")
    
    item_selecionado = st.selectbox(
        "📌 Selecione um Item para Editar/Excluir ou Cadastre um Novo (Pesquise por código, frase, cor ou categoria):", 
        opcoes_prod
    )
    
    dados_item = {}
    is_edicao = False
    if item_selecionado and not item_selecionado.startswith("➕"):
        is_edicao = True
        cod_existente = item_selecionado.split("]")[0].replace("✏ [", "").strip()
        row_match = df_produtos[df_produtos["codigo"] == cod_existente]
        if not row_match.empty:
            dados_item = row_match.iloc[0].to_dict()

    col_qtd_nome = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
    qtd_atual_item = int(pd.to_numeric(dados_item.get(col_qtd_nome, 1), errors="coerce") or 1) if is_edicao else 1

    cod_cur = str(dados_item.get("codigo", ""))
    cache_extras = st.session_state["extra_costs_cache"].get(cod_cur, {})

    val_e_extra_init = float(dados_item.get("estampa_extra") or cache_extras.get("estampa_extra", 0.0))
    val_m_bord_init = float(dados_item.get("matriz_bordado") or cache_extras.get("matriz_bordado", 0.0))

    with st.form("form_compra"):
        c1, c2, c3 = st.columns(3)
        with c1:
            cod_c = st.text_input("Código (ex: BL-0001) *", value=cod_cur, disabled=is_edicao)
            cor_c = st.text_input("Cor do Boné *", value=str(dados_item.get("cor", "")))
        with c2:
            frase_c = st.text_input("Arte Estampada *", value=str(dados_item.get("frase", "")))
            cor_estampa_c = st.text_input("Cor Estampada *", value=str(dados_item.get("cor_estampa", "")))
        with c3:
            cat_opts = ["Básico", "Kids", "Outro", "Premium"]
            cat_val = str(dados_item.get("categoria", "Básico"))
            idx_cat = cat_opts.index(cat_val) if cat_val in cat_opts else 0
            cat_c = st.selectbox("Produto", cat_opts, index=idx_cat)
            custo_c = st.number_input("Custo Base Unitário (R$) *", min_value=0.0, value=float(dados_item.get("custo", 29.0)), format="%.2f")

        c_extra1, c_extra2 = st.columns(2)
        with c_extra1:
            estampa_extra = st.number_input("Estampa Extra (R$)", min_value=0.0, value=val_e_extra_init, format="%.2f")
        with c_extra2:
            matriz_bordado = st.number_input("Matriz Bordado (R$)", min_value=0.0, value=val_m_bord_init, format="%.2f")

        c4_1, c4_2 = st.columns(2)
        with c4_1:
            qtd_comprada = st.number_input(
                "Quantidade Comprada / Estoque *",
                min_value=1,
                value=qtd_atual_item,
                step=1
            )
        with c4_2:
            dt_aquisicao = st.date_input("Data da Aquisição *", datetime.date.today(), format="DD/MM/YYYY")

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            btn_salvar = st.form_submit_button("💾 Salvar / Atualizar Item", use_container_width=True, type="primary")
        with b_col2:
            btn_excluir = st.form_submit_button("🗑 Excluir Item Cadastrado", use_container_width=True)

        if btn_salvar:
            if not cod_c.strip():
                st.error("Informe o código do produto!")
            else:
                custo_base = round(float(custo_c), 2)
                e_extra = round(float(estampa_extra), 2)
                m_bordado = round(float(matriz_bordado), 2)
                
                custo_unit_total = custo_base + e_extra + m_bordado
                valor_compra_total = round(custo_unit_total * int(qtd_comprada), 2)

                novo_prod = {
                    "codigo": cod_c.strip(),
                    "cor": cor_c.strip(),
                    "frase": frase_c.strip(),
                    "cor_estampa": cor_estampa_c.strip(),
                    "categoria": cat_c,
                    "custo": custo_base,
                    "estampa_extra": e_extra,
                    "matriz_bordado": m_bordado,
                    col_qtd_nome: int(qtd_comprada),
                    "qtd_comprada": int(qtd_comprada),
                    "data_aquisicao": str(dt_aquisicao)
                }

                if safe_upsert_produto(novo_prod):
                    if valor_compra_total > 0 and not is_edicao:
                        safe_insert("caixa", {
                            "data": str(dt_aquisicao),
                            "desc": f"Compra de Mercadorias - {cod_c.strip()} ({qtd_comprada}un)",
                            "tipo": "Compra de Mercadorias",
                            "valor": valor_compra_total
                        })

                    st.session_state["flash_success"] = f"🎉 Produto {cod_c} atualizado com sucesso!"
                    st.rerun()

        if btn_excluir:
            if not is_edicao:
                st.error("Selecione um produto existente para excluir!")
            else:
                codigo_alvo = cod_c.strip()
                vendas_relacionadas = False
                if not df_vendas.empty:
                    col_c_venda = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
                    if col_c_venda in df_vendas.columns:
                        vendas_relacionadas = not df_vendas[df_vendas[col_c_venda].astype(str) == codigo_alvo].empty

                if vendas_relacionadas:
                    st.error(f"⛔ Operação Bloqueada! O produto '{codigo_alvo}' possui vendas registradas no sistema e não pode ser excluído.")
                else:
                    try:
                        supabase.table("produtos").delete().eq("codigo", codigo_alvo).execute()
                        st.session_state["flash_success"] = f"🗑️ Produto {codigo_alvo} excluído com sucesso!"
                        st.rerun()
                    except Exception as err_del:
                        st.error(f"Erro ao excluir o produto: {err_del}")

    st.markdown("---")
    st.subheader("📋 Histórico Permanente de Aquisições")
    
    if not df_produtos.empty:
        df_exib_compras = df_produtos.copy()
        
        df_exib_compras["custo_num"] = get_numeric_series(df_exib_compras, "custo")
        
        # Garante a recuperação dos custos de estampa_extra e matriz_bordado localmente se omitidos no DB
        df_exib_compras["estampa_extra_num"] = df_exib_compras.apply(
            lambda r: float(r.get("estampa_extra") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("estampa_extra", 0.0)), axis=1
        )
        df_exib_compras["matriz_bordado_num"] = df_exib_compras.apply(
            lambda r: float(r.get("matriz_bordado") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("matriz_bordado", 0.0)), axis=1
        )
        
        col_q_compra = "qtd_comprada" if "qtd_comprada" in df_exib_compras.columns else ("qtd_estoque" if "qtd_estoque" in df_exib_compras.columns else "qtd")
        df_exib_compras["qtd_num"] = get_numeric_series(df_exib_compras, col_q_compra, 1.0)
        
        df_exib_compras["custo_unitario_composto"] = (
            df_exib_compras["custo_num"] + 
            df_exib_compras["estampa_extra_num"] + 
            df_exib_compras["matriz_bordado_num"]
        )
        df_exib_compras["custo_total_comp"] = df_exib_compras["custo_unitario_composto"] * df_exib_compras["qtd_num"]

        df_exib_compras["Custo Base"] = df_exib_compras["custo_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_exib_compras["Estampa Extra"] = df_exib_compras["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_exib_compras["Matriz Bordado"] = df_exib_compras["matriz_bordado_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_exib_compras["Custo Unitario Total"] = df_exib_compras["custo_unitario_composto"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_exib_compras["Custo Total Compra"] = df_exib_compras["custo_total_comp"].apply(lambda v: f"R$ {float(v):,.2f}")

        mapa_colunas_compras = {
            "codigo": "Código",
            "cor": "Cor do Boné",
            "frase": "Arte Estampada",
            "cor_estampa": "Cor Estampada",
            "categoria": "Produto",
            "Custo Base": "Custo Base",
            "Estampa Extra": "Estampa Extra",
            "Matriz Bordado": "Matriz Bordado",
            "Custo Unitario Total": "Custo Unit. Total",
            "Custo Total Compra": "Custo Total Lote"
        }
        
        cols_compras = [
            "codigo", "cor", "frase", "cor_estampa", "categoria", 
            "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Unitario Total", "Custo Total Compra"
        ]
        cols_compras_existentes = [c for c in cols_compras if c in df_exib_compras.columns]
        
        st.dataframe(df_exib_compras[cols_compras_existentes].rename(columns=mapa_colunas_compras), use_container_width=True, hide_index=True)

elif menu == "📦 Estoque":
    st.subheader("📦 Estoque Atual")
    
    if not df_produtos.empty:
        df_est = df_produtos.copy()
        col_qtd_est = "qtd_estoque" if "qtd_estoque" in df_est.columns else ("qtd" if "qtd" in df_est.columns else "estoque")
        
        qtds_est_num = get_numeric_series(df_est, col_qtd_est)
        df_est["Status"] = qtds_est_num.apply(lambda val: "Disponível" if val > 0 else "Esgotado")
        
        with st.expander("🔍 Consultar e Pesquisar no Estoque", expanded=True):
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                busca_texto = st.text_input("Pesquisar por Código ou Arte:")
            with c_f2:
                cat_unicas = ["Todas"] + sorted(list(df_est["categoria"].dropna().unique())) if "categoria" in df_est.columns else ["Todas"]
                filtro_cat = st.selectbox("Filtrar por Produto/Categoria:", cat_unicas)
            with c_f3:
                cor_unicas = ["Todas"] + sorted(list(df_est["cor"].dropna().unique())) if "cor" in df_est.columns else ["Todas"]
                filtro_cor = st.selectbox("Filtrar por Cor do Boné:", cor_unicas)

            df_est_filtrado = df_est.copy()
            if busca_texto:
                df_est_filtrado = df_est_filtrado[
                    df_est_filtrado["codigo"].astype(str).str.contains(busca_texto, case=False, na=False) |
                    df_est_filtrado.get("frase", pd.Series([""]*len(df_est_filtrado))).astype(str).str.contains(busca_texto, case=False, na=False)
                ]
            if filtro_cat != "Todas" and "categoria" in df_est_filtrado.columns:
                df_est_filtrado = df_est_filtrado[df_est_filtrado["categoria"] == filtro_cat]
            if filtro_cor != "Todas" and "cor" in df_est_filtrado.columns:
                df_est_filtrado = df_est_filtrado[df_est_filtrado["cor"] == filtro_cor]

        if "custo" in df_est_filtrado.columns:
            df_est_filtrado["custo"] = get_numeric_series(df_est_filtrado, "custo").apply(lambda v: f"R$ {float(v):,.2f}")

        mapa_colunas_est = {
            "codigo": "Código",
            "cor": "Cor do Boné",
            "frase": "Arte Estampada",
            "cor_estampa": "Cor Estampada",
            "categoria": "Produto",
            "custo": "Custo Base",
            col_qtd_est: "Estoque",
            "Status": "Status"
        }
        
        cols_est = [col for col in [
            "codigo", "cor", "frase", "cor_estampa", "categoria", "custo", 
            col_qtd_est, "Status"
        ] if col in df_est_filtrado.columns]

        st.dataframe(df_est_filtrado[cols_est].rename(columns=mapa_colunas_est), use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif menu == "🛒 Vendas":
    st.subheader("🛒 Lançar Nova Venda")
    
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        c_qtd_p = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
        qtds_p = get_numeric_series(df_produtos, c_qtd_p)
        
        opts = [f"[{r['codigo']}] \"{r.get('frase','')}\" (Disponível: {int(pd.to_numeric(r.get(c_qtd_p, 0), errors='coerce') or 0)} un)" for _, r in df_produtos.iterrows()]
        
        if opts:
            busca_bone = st.text_input("🔍 Pesquisar Boné no Estoque (por código, frase ou cor):", "")
            opts_filtradas = opts
            if busca_bone.strip():
                opts_filtradas = [o for o in opts if busca_bone.lower() in o.lower()]

            if opts_filtradas:
                prod_sel = st.selectbox("Selecione o Boné Encontrado *", opts_filtradas)
                codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""
                
                p_match = df_produtos[df_produtos["codigo"] == codigo_sel]
                estoque_disp = int(pd.to_numeric(p_match.iloc[0].get(c_qtd_p, 0), errors="coerce") or 0) if not p_match.empty else 0
                max_qtd = max(1, estoque_disp)

                c1, c2, c3 = st.columns(3)
                with c1:
                    qtd_venda = st.number_input("Quantidade *", min_value=1, max_value=max(1, max_qtd), value=1, step=1, help=f"Quantidade disponível em estoque: {estoque_disp}")
                    cliente = st.text_input("Nome do Cliente *")
                with c2:
                    valor_venda = st.number_input("Valor Total (R$) *", min_value=0.0, value=60.0, step=5.0, format="%.2f")
                    forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])
                with c3:
                    data_venda = st.date_input("Data da Venda *", datetime.date.today(), format="DD/MM/YYYY")
                    data_receb = st.date_input("Data de Recebimento (Opcional)", value=None, format="DD/MM/YYYY")

                if st.button("🚀 Finalizar Venda", type="primary", use_container_width=True):
                    if not cliente.strip():
                        st.error("Informe o nome do cliente!")
                    else:
                        p_info = df_produtos[df_produtos["codigo"] == codigo_sel].iloc[0]
                        custo_base = float(pd.to_numeric(p_info.get("custo", 0.0), errors="coerce") or 0.0)
                        
                        cache_ex = st.session_state["extra_costs_cache"].get(codigo_sel, {})
                        estampa_ex = float(p_info.get("estampa_extra") or cache_ex.get("estampa_extra", 0.0))
                        matriz_b = float(p_info.get("matriz_bordado") or cache_ex.get("matriz_bordado", 0.0))
                        
                        custo_unit_composto = custo_base + estampa_ex + matriz_b
                        dt_receb_str = str(data_receb) if data_receb is not None else None

                        val_venda_fmt = round(float(valor_venda), 2)
                        custo_calc_fmt = round(float(custo_unit_composto * qtd_venda), 2)

                        payload_venda = {
                            "codigo_bone": codigo_sel,
                            "codigo": codigo_sel,
                            "cliente": cliente.strip(),
                            "qtd": int(qtd_venda),
                            "valor_venda": val_venda_fmt,
                            "forma_pagto": forma_pagto,
                            "data": str(data_venda),
                            "data_venda": str(data_venda),
                            "custo": custo_calc_fmt,
                            "custo_unitario": round(float(custo_unit_composto), 2)
                        }
                        if dt_receb_str:
                            payload_venda["data_recebimento"] = dt_receb_str

                        if safe_insert("vendas", payload_venda):
                            novo_estoque = max(0, estoque_disp - int(qtd_venda))
                            supabase.table("produtos").update({c_qtd_p: novo_estoque}).eq("codigo", codigo_sel).execute()

                            if dt_receb_str and val_venda_fmt > 0:
                                safe_insert("caixa", {
                                    "data": dt_receb_str,
                                    "desc": f"Venda {codigo_sel} ({qtd_venda}un) - {cliente.strip()}",
                                    "tipo": "Venda",
                                    "valor": val_venda_fmt
                                })
                                
                            st.session_state["flash_success"] = f"🎉 Venda salva e estoque atualizado com sucesso!"
                            st.rerun()
            else:
                st.warning("Nenhum produto correspondente à busca encontrado.")
    else:
        st.info("Nenhum produto cadastrado no banco de dados. Cadastre primeiro em Compras.")

    st.markdown("---")
    st.subheader("⏳ Vendas Pendentes de Recebimento")
    
    if not df_vendas.empty:
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_vendas.columns else ("data_receb" if "data_receb" in df_vendas.columns else None)
        if col_dt_rec:
            df_pendentes = df_vendas[df_vendas[col_dt_rec].isna() | (df_vendas[col_dt_rec] == "") | (df_vendas[col_dt_rec] == "None")].copy()
        else:
            df_pendentes = pd.DataFrame()

        if not df_pendentes.empty:
            c_val_p = "valor_venda" if "valor_venda" in df_pendentes.columns else ("valor" if "valor" in df_pendentes.columns else "valor_total")
            opts_pend = [f"ID {r['id']} | {r.get('cliente','')} - R$ {round(float(r.get(c_val_p, 0.0)), 2):,.2f} (Venda: {format_data_br(r.get('data',''))})" for _, r in df_pendentes.iterrows()]
            venda_sel = st.selectbox("📌 Selecione uma Venda para Gerenciar / Confirmar Recebimento:", opts_pend)
            
            c_rec1, c_rec2, c_rec3 = st.columns([2, 2, 1])
            with c_rec1:
                dt_confirmada = st.date_input("Data Efetiva de Recebimento *", datetime.date.today(), key="dt_conf_rec", format="DD/MM/YYYY")
            with c_rec2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Confirmar Recebimento", use_container_width=True, type="primary"):
                    venda_id = int(venda_sel.split("|")[0].replace("ID", "").strip())
                    row_v = df_pendentes[df_pendentes["id"] == venda_id].iloc[0]
                    
                    supabase.table("vendas").update({col_dt_rec: str(dt_confirmada)}).eq("id", venda_id).execute()
                    
                    c_cod = "codigo_bone" if "codigo_bone" in row_v else ("codigo" if "codigo" in row_v else "codigo_produto")
                    val_rec_fmt = round(float(row_v.get(c_val_p, 0.0)), 2)
                    
                    if val_rec_fmt > 0:
                        safe_insert("caixa", {
                            "data": str(dt_confirmada),
                            "desc": f"Venda {row_v.get(c_cod,'')} ({row_v.get('qtd',1)}un) - {row_v.get('cliente','')}",
                            "tipo": "Venda",
                            "valor": val_rec_fmt
                        })
                    
                    st.success("🎉 Recebimento confirmado e lançado no caixa!")
                    st.rerun()

            with c_rec3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑 Excluir Venda Incorreta", use_container_width=True, type="secondary"):
                    venda_id = int(venda_sel.split("|")[0].replace("ID", "").strip())
                    row_v = df_pendentes[df_pendentes["id"] == venda_id].iloc[0]
                    
                    cod_prod_excluir = row_v.get("codigo_bone") or row_v.get("codigo") or row_v.get("codigo_produto")
                    qtd_venda_excluir = int(row_v.get("qtd") or row_v.get("quantidade") or 1)
                    estornar_estoque(cod_prod_excluir, qtd_venda_excluir)

                    supabase.table("vendas").delete().eq("id", venda_id).execute()
                    st.session_state["flash_success"] = "🗑️ Venda excluída e produtos estornados ao estoque com sucesso!"
                    st.rerun()

            df_pend_exib = df_pendentes.copy()
            col_d_v = "data_venda" if "data_venda" in df_pend_exib.columns else "data"
            col_c_b = "codigo_bone" if "codigo_bone" in df_pend_exib.columns else "codigo"
            col_cli = "cliente" if "cliente" in df_pend_exib.columns else "nome_cliente"
            col_val = "valor_venda" if "valor_venda" in df_pend_exib.columns else "valor"
            col_pag = "forma_pagto" if "forma_pagto" in df_pend_exib.columns else "pagto"

            df_tabela_pend = pd.DataFrame({
                "Data da Venda": df_pend_exib[col_d_v].apply(format_data_br) if col_d_v in df_pend_exib.columns else "",
                "Código": df_pend_exib.get(col_c_b, ""),
                "Cliente": df_pend_exib.get(col_cli, ""),
                "Valor": get_numeric_series(df_pend_exib, col_val).apply(lambda v: f"R$ {float(v):,.2f}"),
                "Forma de Pagamento": df_pend_exib.get(col_pag, "")
            })
            st.dataframe(df_tabela_pend, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma venda pendente de recebimento no momento.")
    else:
        st.info("Nenhuma venda registrada.")

    st.markdown("---")
    st.subheader("📋 Histórico Detalhado de Vendas")
    if not df_vendas.empty:
        df_v_exib = df_vendas.copy()
        col_d_v = "data_venda" if "data_venda" in df_v_exib.columns else "data"
        col_c_b = "codigo_bone" if "codigo_bone" in df_v_exib.columns else "codigo"
        col_cli = "cliente" if "cliente" in df_v_exib.columns else "nome_cliente"
        col_val = "valor_venda" if "valor_venda" in df_v_exib.columns else "valor"
        col_pag = "forma_pagto" if "forma_pagto" in df_v_exib.columns else "pagto"

        st.markdown("##### ⚙️ Vendas Cadastradas")
        
        if "editing_venda_id" not in st.session_state:
            st.session_state["editing_venda_id"] = None

        for idx, row in df_v_exib.iterrows():
            v_id = row["id"]
            c_data_exib = format_data_br(row.get(col_d_v, ""))
            c_cod_exib = row.get(col_c_b, "")
            c_cli_exib = row.get(col_cli, "")
            c_val_exib = float(pd.to_numeric(row.get(col_val, 0.0), errors="coerce") or 0.0)
            c_pag_exib = row.get(col_pag, "PIX")

            c_dt, c_cod, c_cli, c_vlr, c_pg, c_act1, c_act2 = st.columns([2, 1.5, 2.5, 1.5, 2, 1, 1])
            with c_dt:
                st.write(f"**Data:** {c_data_exib}")
            with c_cod:
                st.write(f"**Código:** {c_cod_exib}")
            with c_cli:
                st.write(f"**Cliente:** {c_cli_exib}")
            with c_vlr:
                st.write(f"**Valor:** R$ {c_val_exib:,.2f}")
            with c_pg:
                st.write(f"**Pagto:** {c_pag_exib}")
            with c_act1:
                if st.button("✏ Alterar", key=f"btn_edit_row_{v_id}", use_container_width=True):
                    st.session_state["editing_venda_id"] = v_id
                    st.rerun()
            with c_act2:
                if st.button("🗑 Excluir", key=f"btn_del_row_{v_id}", use_container_width=True):
                    cod_prod_e = row.get("codigo_bone") or row.get("codigo") or row.get("codigo_produto")
                    qtd_venda_e = int(row.get("qtd") or row.get("quantidade") or 1)
                    estornar_estoque(cod_prod_e, qtd_venda_e)

                    supabase.table("vendas").delete().eq("id", v_id).execute()
                    st.session_state["flash_success"] = f"🗑️ Venda ID {v_id} excluída com sucesso!"
                    st.rerun()

            if st.session_state.get("editing_venda_id") == v_id:
                with st.form(key=f"form_edit_row_{v_id}"):
                    st.markdown(f"##### ✏ Editar Venda ID {v_id}")
                    e_col1, e_col2, e_col3 = st.columns(3)
                    with e_col1:
                        e_cliente = st.text_input("Cliente *", value=str(c_cli_exib))
                    with e_col2:
                        e_valor = st.number_input("Valor (R$) *", min_value=0.0, value=float(c_val_exib), format="%.2f")
                    with e_col3:
                        opts_pag = ["PIX", "Cartão", "Dinheiro", "Brinde"]
                        idx_pag = opts_pag.index(c_pag_exib) if c_pag_exib in opts_pag else 0
                        e_forma_pagto = st.selectbox("Forma Pagto *", opts_pag, index=idx_pag)

                    btn_salvar_e, btn_cancel_e = st.columns(2)
                    with btn_salvar_e:
                        if st.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary"):
                            supabase.table("vendas").update({
                                "cliente": e_cliente.strip(),
                                "valor_venda": round(float(e_valor), 2),
                                "forma_pagto": e_forma_pagto
                            }).eq("id", v_id).execute()
                            st.session_state["editing_venda_id"] = None
                            st.session_state["flash_success"] = f"🎉 Venda ID {v_id} atualizada com sucesso!"
                            st.rerun()
                    with btn_cancel_e:
                        if st.form_submit_button("❌ Cancelar", use_container_width=True):
                            st.session_state["editing_venda_id"] = None
                            st.rerun()
            st.markdown("<hr style='margin: 4px 0;'>", unsafe_allow_html=True)

elif menu == "💵 Custos":
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷️ Custos de Venda", "🎪 Feiras"], horizontal=True)

    if sub_tab == "📦 Mercadorias":
        if not df_produtos.empty:
            df_m = df_produtos.copy()
            col_custo = "custo" if "custo" in df_m.columns else "custo_unitario"
            col_data_aq = "data_aquisicao" if "data_aquisicao" in df_m.columns else "created_at"

            df_m["custo_num"] = get_numeric_series(df_m, col_custo)
            df_m["estampa_extra_num"] = df_m.apply(
                lambda r: float(r.get("estampa_extra") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("estampa_extra", 0.0)), axis=1
            )
            df_m["matriz_bordado_num"] = df_m.apply(
                lambda r: float(r.get("matriz_bordado") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("matriz_bordado", 0.0)), axis=1
            )
            
            col_qtd_ref = "qtd_comprada" if "qtd_comprada" in df_m.columns else ("qtd_estoque" if "qtd_estoque" in df_m.columns else "qtd")
            df_m["qtd_num"] = get_numeric_series(df_m, col_qtd_ref, 1.0)
            
            df_m["custo_composto_unitario"] = df_m["custo_num"] + df_m["estampa_extra_num"] + df_m["matriz_bordado_num"]
            df_m["Custo Total Calc"] = df_m["custo_composto_unitario"] * df_m["qtd_num"]
            df_m["Data_Formatada"] = df_m[col_data_aq].apply(format_data_br) if col_data_aq in df_m.columns else ""

            st.markdown("##### 📊 Resumo Agrupado por Data da Aquisição")
            agrup_data = df_m.groupby("Data_Formatada").agg({
                "qtd_num": "sum",
                "Custo Total Calc": "sum"
            }).reset_index().rename(columns={"Data_Formatada": "Data da Aquisição", "qtd_num": "Quantidade Comprada"})

            agrup_data["Custo Total"] = agrup_data["Custo Total Calc"].apply(lambda v: f"R$ {float(v):,.2f}")
            st.dataframe(agrup_data[["Data da Aquisição", "Quantidade Comprada", "Custo Total"]], use_container_width=True, hide_index=True)

            with st.expander("🔍 Visualizar Registros Individuais de Compras", expanded=False):
                df_m["Custo Base"] = df_m["custo_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_m["Estampa Extra"] = df_m["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_m["Matriz Bordado"] = df_m["matriz_bordado_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_m["Custo Unit. Total"] = df_m["custo_composto_unitario"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_m["Custo Total"] = df_m["Custo Total Calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                
                cols_ind = [c for c in ["codigo", "categoria", "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Unit. Total", "Custo Total", "Data_Formatada"] if c in df_m.columns]
                st.dataframe(df_m[cols_ind], use_container_width=True, hide_index=True)

    elif sub_tab == "🏷️ Custos de Venda":
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
                
                payload_cv = {
                    "subcategoria": "Custos de Venda",
                    "data": str(dt_cv),
                    "desc": desc_cv.strip(),
                    "tipo": tipo_cv,
                    "valor": val_cv_fmt
                }
                
                if safe_insert("custos_avulsos", payload_cv):
                    safe_insert("caixa", {
                        "data": str(dt_cv), 
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
                for idx, row in df_cv_exib.iterrows():
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
                        if st.button("🗑 Excluir", key=f"del_cv_{c_id}", use_container_width=True):
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

    elif sub_tab == "🎪 Feiras":
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
                
                payload_cf = {
                    "subcategoria": "Feiras",
                    "data": str(dt_cf),
                    "desc": f"Feira: {feira_cf.strip()} - {desc_cf.strip()}",
                    "tipo": tipo_cf,
                    "valor": val_cf_fmt
                }
                
                if safe_insert("custos_avulsos", payload_cf):
                    safe_insert("caixa", {
                        "data": str(dt_cf), 
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
                for idx, row in df_cf_exib.iterrows():
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
                        if st.button("🗑 Excluir", key=f"del_cf_{f_id}", use_container_width=True):
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
                st.info("Nenum custo de feira registrado até o momento.")
        else:
            st.info("Nenhum custo registrado.")

elif menu == "🤝 Aportes dos Sócios":
    st.subheader("🤝 Registro de Aportes e Devoluções")
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_ap = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
    with c2:
        socio_ap = st.selectbox("Sócio *", ["Renan", "Ronald"])
    with c3:
        val_ap = st.number_input("Valor (R$) *", min_value=1.0, value=100.0, format="%.2f")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🤝 Registrar Aporte", use_container_width=True, type="primary"):
            val_ap_fmt = round(float(val_ap), 2)
            payload_ap = {
                "data": str(dt_ap),
                "socio": socio_ap,
                "valor": val_ap_fmt,
                "tipo": "Aporte"
            }
            if safe_insert("aportes", payload_ap):
                safe_insert("caixa", {
                    "data": str(dt_ap),
                    "desc": f"Aporte ({socio_ap})",
                    "tipo": "Aporte de Sócio",
                    "valor": val_ap_fmt
                })
                st.session_state["flash_success"] = f"Aporte de R$ {val_ap_fmt:,.2f} registrado com sucesso!"
                st.rerun()

    with col_btn2:
        if st.button("🔄 Devolução de Aporte", use_container_width=True):
            val_ap_fmt = round(float(val_ap), 2)
            payload_dev = {
                "data": str(dt_ap),
                "socio": socio_ap,
                "valor": -val_ap_fmt,
                "tipo": "Devolução"
            }
            if safe_insert("aportes", payload_dev):
                safe_insert("caixa", {
                    "data": str(dt_ap),
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

        for idx, row in df_aportes.iterrows():
            ap_id = row.get("id")
            ap_dt = format_data_br(row.get("data") or row.get("created_at"))
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
                if st.button("✏ Alterar", key=f"edit_ap_{ap_id}", use_container_width=True):
                    st.session_state["editing_aporte_id"] = ap_id
                    st.rerun()
            with c6:
                if st.button("🗑 Excluir", key=f"del_ap_{ap_id}", use_container_width=True):
                    supabase.table("aportes").delete().eq("id", ap_id).execute()
                    st.session_state["flash_success"] = f"Registro ID {ap_id} excluído com sucesso!"
                    st.rerun()

            if st.session_state.get("editing_aporte_id") == ap_id:
                with st.form(key=f"form_edit_ap_{ap_id}"):
                    st.markdown(f"##### ✏ Editar Registro ID {ap_id}")
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
        st.info("Nenhum aporte ou devolução registrado no momento.")

elif menu == "💰 Fluxo de Caixa":
    st.subheader("💰 Extrato Consolidado de Fluxo de Caixa")
    
    lista_movimentos = []

    # 1. Compras do Módulo de Compras (Agrupadas por dia)
    if not df_produtos.empty:
        df_p_compra = df_produtos.copy()
        col_dt_compra = "data_aquisicao" if "data_aquisicao" in df_p_compra.columns else "created_at"
        
        df_p_compra["data_str"] = df_p_compra[col_dt_compra].astype(str).str.slice(0, 10) if col_dt_compra in df_p_compra.columns else ""
        
        custo_b = get_numeric_series(df_p_compra, "custo")
        
        est_ex = df_p_compra.apply(
            lambda r: float(r.get("estampa_extra") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("estampa_extra", 0.0)), axis=1
        )
        mat_bd = df_p_compra.apply(
            lambda r: float(r.get("matriz_bordado") or st.session_state["extra_costs_cache"].get(str(r.get("codigo")), {}).get("matriz_bordado", 0.0)), axis=1
        )
        
        df_p_compra["custo_composto_unit"] = custo_b + est_ex + mat_bd
        
        col_q = "qtd_comprada" if "qtd_comprada" in df_p_compra.columns else ("qtd_estoque" if "qtd_estoque" in df_p_compra.columns else "qtd")
        df_p_compra["qtd_num"] = get_numeric_series(df_p_compra, col_q, 1.0)
        df_p_compra["qtd_num"] = df_p_compra["qtd_num"].apply(lambda v: max(1, int(v)))
        
        df_p_compra["custo_total_item"] = df_p_compra["custo_composto_unit"] * df_p_compra["qtd_num"]
        
        agrup_compras = df_p_compra.groupby("data_str").agg(
            total_custo=("custo_total_item", "sum"),
            total_qtd=("qtd_num", "sum")
        ).reset_index()
        
        for _, r in agrup_compras.iterrows():
            dt_c = r["data_str"]
            tot_c = float(r["total_custo"])
            tot_qtd = int(r["total_qtd"])
            if tot_c > 0:
                lista_movimentos.append({
                    "Data_Val": dt_c,
                    "Data": format_data_br(dt_c),
                    "Origem": "🛍️ Módulo Compras",
                    "Descrição": f"Compra Agrupada ({tot_qtd} itens adquiridos)",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -tot_c
                })

    # 2. Recebimentos das Vendas
    if not df_vendas.empty:
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_vendas.columns else ("data_receb" if "data_receb" in df_vendas.columns else "data")
        for _, r in df_vendas.iterrows():
            dt_v = r.get(col_dt_rec) or r.get("data")
            val_v = float(pd.to_numeric(r.get("valor_venda") or r.get("valor") or 0.0, errors="coerce") or 0.0)
            cli = r.get("cliente") or r.get("nome_cliente") or ""
            cod = r.get("codigo_bone") or r.get("codigo") or ""
            if val_v > 0:
                lista_movimentos.append({
                    "Data_Val": str(dt_v),
                    "Data": format_data_br(dt_v),
                    "Origem": "🛒 Recebimento de Vendas",
                    "Descrição": f"Venda {cod} - Cliente: {cli}",
                    "Tipo": "Entrada 🟢",
                    "Valor_Num": val_v
                })

    # 3. Custos de Venda e Custos das Feiras
    if not df_custos.empty:
        for _, r in df_custos.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            sub_c = str(r.get("subcategoria", "Custos"))
            desc_c = r.get("desc") or r.get("descricao") or "Despesa Avulsa"
            origem_tag = "🏷️ Custos de Venda" if "venda" in sub_c.lower() else ("🎪 Custos de Feiras" if "feira" in sub_c.lower() else f"💵 Custos ({sub_c})")
            if val_c > 0:
                lista_movimentos.append({
                    "Data_Val": str(r.get("data")),
                    "Data": format_data_br(r.get("data")),
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
            dt_ap_raw = r.get("data") or r.get("created_at") or r.get("data_aporte")
            
            if val_ap != 0:
                is_devolucao = "devoluc" in tipo_ap.lower() or val_ap < 0
                nome_op = "Devolução" if is_devolucao else "Aporte"
                
                lista_movimentos.append({
                    "Data_Val": str(dt_ap_raw),
                    "Data": format_data_br(dt_ap_raw),
                    "Origem": "🤝 Aporte dos Sócios",
                    "Descrição": f"{nome_op} ({socio})",
                    "Tipo": "Saída 🔴" if is_devolucao else "Entrada 🟢",
                    "Valor_Num": -abs(val_ap) if is_devolucao else abs(val_ap)
                })

    if lista_movimentos:
        df_extrato = pd.DataFrame(lista_movimentos)
        
        df_extrato["Data_Raw"] = pd.to_datetime(df_extrato["Data_Val"], errors="coerce")
        df_extrato["Data_Raw"] = df_extrato["Data_Raw"].fillna(pd.Timestamp("1970-01-01"))
        
        df_extrato = df_extrato.sort_values(by="Data_Raw", ascending=True).reset_index(drop=True)
        
        df_extrato["Saldo_Acumulado"] = df_extrato["Valor_Num"].cumsum()
        df_extrato["Valor (R$)"] = df_extrato["Valor_Num"].apply(lambda v: f"R$ {v:,.2f}")
        df_extrato["Saldo Acumulado (R$)"] = df_extrato["Saldo_Acumulado"].apply(lambda v: f"R$ {v:,.2f}")

        cols_final = ["Data", "Origem", "Descrição", "Tipo", "Valor (R$)", "Saldo Acumulado (R$)"]
        st.dataframe(df_extrato[cols_final], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada no fluxo de caixa.")

elif menu == "📥 Importação":
    st.subheader("📥 Importação de Dados em Lote")
    st.markdown("Selecione o tipo de dado que deseja importar e envie o arquivo Excel (.xlsx) ou CSV (.csv).")

    tipo_import = st.selectbox("Escolha o destino dos dados *", ["🛍️ Compras (Produtos)", "🛒 Vendas"])

    with st.expander("📌 Baixar Modelos de Planilha para Importação", expanded=True):
        st.markdown("Utilize os modelos abaixo para garantir que os arquivos estejam com as colunas corretas antes do envio:")
        c_mod1, c_mod2 = st.columns(2)
        with c_mod1:
            df_modelo_compras = pd.DataFrame([{
                "codigo": "BL-0001",
                "cor": "Preto",
                "frase": "Vista o que voce pensa",
                "cor_estampa": "Branco",
                "categoria": "Básico",
                "custo": 29.00,
                "estampa_extra": 0.00,
                "matriz_bordado": 0.00,
                "qtd_estoque": 10,
                "data_aquisicao": "2026-10-04"
            }])
            output_c = io.BytesIO()
            with pd.ExcelWriter(output_c, engine='openpyxl') as writer:
                df_modelo_compras.to_excel(writer, index=False, sheet_name="Modelo_Compras")
            st.download_button(
                "📥 Baixar Modelo de Compras (.xlsx)",
                data=output_c.getvalue(),
                file_name="Modelo_Importacao_Compras.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with c_mod2:
            df_modelo_vendas = pd.DataFrame([{
                "codigo_bone": "BL-0001",
                "cliente": "João Silva",
                "qtd": 2,
                "valor_venda": 120.00,
                "forma_pagto": "PIX",
                "data": "2026-10-04",
                "data_recebimento": "2026-10-04",
                "custo": 58.00
            }])
            output_v = io.BytesIO()
            with pd.ExcelWriter(output_v, engine='openpyxl') as writer:
                df_modelo_vendas.to_excel(writer, index=False, sheet_name="Modelo_Vendas")
            st.download_button(
                "📥 Baixar Modelo de Vendas (.xlsx)",
                data=output_v.getvalue(),
                file_name="Modelo_Importacao_Vendas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    st.markdown("---")
    file_imp = st.file_uploader("Carregar planilha (.xlsx ou .csv)", type=["xlsx", "csv"])

    if file_imp is not None:
        try:
            if file_imp.name.endswith(".csv"):
                df_imp = pd.read_csv(file_imp)
            else:
                df_imp = pd.read_excel(file_imp)

            st.markdown("##### 🔍 Pré-visualização dos dados a serem importados:")
            st.dataframe(df_imp.head(10), use_container_width=True)

            if st.button("🚀 Confirmar e Importar para o Banco de Dados", type="primary", use_container_width=True):
                registros = df_imp.to_dict(orient="records")
                if tipo_import == "🛍️ Compras (Produtos)":
                    supabase.table("produtos").upsert(registros, on_conflict="codigo").execute()
                else:
                    supabase.table("vendas").insert(registros).execute()

                st.success("🎉 Importação realizada com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")

elif menu == "💾 Gestão de Dados":
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
    st.markdown("#### ⚙️ Operações de Banco Supabase")
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
