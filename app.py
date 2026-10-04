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

    /* Container do Cabeçalho Padrão (Sem Logo) */
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

    /* Ajuste na altura do cabeçalho para exibir a imagem de forma sutil */
    div[data-testid="stImage"] > img {
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.08);
        margin-bottom: 10px;
        width: 100% !important;
        max-height: 120px !important;
        object-fit: cover !important;
    }

    /* Cards de KPIs */
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

# Função auxiliar para formatar datas no padrão brasileiro DD/MM/AAAA
def format_data_br(val):
    if not val or pd.isna(val) or str(val).strip().lower() in ["none", "nat", "nan", ""]:
        return ""
    try:
        dt = pd.to_datetime(val)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(val)

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
    except Exception:
        return pd.DataFrame()

# Buscar logo gravada no banco de dados
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

# Salvar logo no banco
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
        st.error(f"Erro ao salvar no Supabase: {e}")
        return False

# Deletar logo do banco
def delete_logo_from_db():
    if not supabase:
        return
    try:
        supabase.table("configuracoes").delete().eq("chave", "logo_header").execute()
        get_saved_logo.clear()
    except Exception as e:
        st.error(f"Erro ao remover no Supabase: {e}")

# Carregar tabelas de dados
df_produtos = fetch_data("produtos")
df_vendas = fetch_data("vendas")
df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")

# Carregar logo persistente do Supabase
if "current_logo" not in st.session_state:
    st.session_state["current_logo"] = get_saved_logo()

# 3. Sidebar (Barra Lateral)
with st.sidebar:
    st.markdown("### 📌 Módulos do Sistema")
    menu = st.radio(
        "Navegue entre os módulos:",
        ["📈 Dashboard", "🛍️ Compras", "📦 Estoque", "🛒 Vendas", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "📥 Importação", "💾 Gestão de Dados"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    
    # Personalização da Logomarca
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
            if st.button("🗑️ Excluir Logo Atual", use_container_width=True, type="secondary"):
                delete_logo_from_db()
                st.session_state["current_logo"] = None
                st.success("Logo removida permanentemente!")
                st.rerun()

# 4. Exibição do Cabeçalho Principal
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

# 5. Lógica dos Módulos
if menu == "📈 Dashboard":
    st.subheader("📈 Dashboard Executivo")
    
    col_v_val = "valor" if "valor" in df_vendas.columns else ("valor_total" if "valor_total" in df_vendas.columns else None)
    total_faturado = float(df_vendas[col_v_val].sum()) if not df_vendas.empty and col_v_val else 0.0
    total_cmv = float(df_vendas["custo"].sum()) if not df_vendas.empty and "custo" in df_vendas.columns else 0.0

    saldo_caixa = 0.0
    if not df_caixa.empty and "valor" in df_caixa.columns and "tipo" in df_caixa.columns:
        entradas = df_caixa[df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saidas = df_caixa[~df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saldo_caixa = float(entradas - saidas)

    total_estoque_qtd = 0
    if not df_produtos.empty:
        col_qtd_p = "qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else ("qtd_estoque" if "qtd_estoque" in df_produtos.columns else None))
        if col_qtd_p:
            total_estoque_qtd = int(pd.to_numeric(df_produtos[col_qtd_p], errors="coerce").fillna(0).sum())

    # Cards de KPIs
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ️</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV Total <span class="tooltip-icon" title="Custo das mercadorias vendidas nos bonés faturados">ℹ️</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo financeiro líquido acumulado">ℹ️</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Itens no Estoque <span class="tooltip-icon" title="Quantidade total de bonés disponíveis no estoque">ℹ️</span></div><div class="kpi-value">{total_estoque_qtd} un</div></div>', unsafe_allow_html=True)

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
        if not df_vendas_fil.empty and ("codigo" in df_vendas_fil.columns or "codigo_produto" in df_vendas_fil.columns) and not df_produtos.empty:
            c_v_col = "codigo" if "codigo" in df_vendas_fil.columns else "codigo_produto"
            df_m = df_vendas_fil.merge(df_produtos, left_on=c_v_col, right_on="codigo", how="left")
            cor_col = "cor" if "cor" in df_m.columns else "cor_x"
            if cor_col in df_m.columns:
                qtd_col = "qtd_x" if "qtd_x" in df_m.columns else ("qtd" if "qtd" in df_m.columns else "qtd_y")
                agrup_cor = df_m.groupby(cor_col)[qtd_col].sum().reset_index()
                fig2 = px.pie(agrup_cor, names=cor_col, values=qtd_cor, hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sem informação de cor cadastrada.")
        else:
            st.info("Nenhuma venda registrada.")

elif menu == "🛒 Vendas":
    st.subheader("🛒 Lançar Nova Venda")
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        c_qtd_p = "qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else ("qtd_estoque" if "qtd_estoque" in df_produtos.columns else None))
        opts = [f"[{r['codigo']}] \"{r.get('frase','')}\" (Disponível: {r.get(c_qtd_p, 0) if c_qtd_p else 0} un)" for _, r in df_produtos.iterrows()]
        prod_sel = st.selectbox("🔍 Selecionar Boné do Estoque *", opts)
        
        codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""
        
        p_match = df_produtos[df_produtos["codigo"] == codigo_sel]
        estoque_disp = int(pd.to_numeric(p_match.iloc[0].get(c_qtd_p, 1), errors="coerce")) if not p_match.empty and c_qtd_p else 1
        max_qtd = max(1, estoque_disp)

        c1, c2, c3 = st.columns(3)
        with c1:
            qtd_venda = st.number_input("Quantidade *", min_value=1, max_value=max_qtd, value=1, step=1, help=f"Quantidade máxima disponível em estoque: {max_qtd}")
            cliente = st.text_input("Nome do Cliente *")
        with c2:
            valor_venda = st.number_input("Valor Total (R$) *", min_value=0.0, value=60.0, step=5.0)
            forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])
        with c3:
            data_venda = st.date_input("Data da Venda *", datetime.date.today(), format="DD/MM/YYYY")
            data_receb = st.date_input("Data de Recebimento (Opcional)", value=None, format="DD/MM/YYYY")

        if st.button("🚀 Finalizar Venda", type="primary", use_container_width=True):
            if not cliente.strip():
                st.error("Informe o nome do cliente!")
            else:
                p_info = df_produtos[df_produtos["codigo"] == codigo_sel].iloc[0]
                custo_unit = float(p_info.get("custo", 0.0))
                dt_receb_str = str(data_receb) if data_receb is not None else None

                # Mapeamento com os aliases mais comuns de banco para prevenir falhas de coluna
                raw_venda = {
                    "cliente": cliente.strip(),
                    "nome_cliente": cliente.strip(),
                    "qtd": int(qtd_venda),
                    "quantidade": int(qtd_venda),
                    "valor": float(valor_venda),
                    "valor_total": float(valor_venda),
                    "forma_pagto": forma_pagto,
                    "pagto": forma_pagto,
                    "data": str(data_venda),
                    "data_venda": str(data_venda),
                    "custo": float(custo_unit * qtd_venda),
                    "codigo": codigo_sel,
                    "codigo_produto": codigo_sel
                }
                if dt_receb_str:
                    raw_venda["data_recebimento"] = dt_receb_str

                # Filtro dinâmico rigoroso: envia APENAS as colunas existentes na tabela 'vendas'
                cols_vendas = df_vendas.columns.tolist() if not df_vendas.empty else []
                if cols_vendas:
                    payload_venda = {k: v for k, v in raw_venda.items() if k in cols_vendas}
                else:
                    payload_venda = {
                        "qtd": int(qtd_venda),
                        "cliente": cliente.strip(),
                        "valor": float(valor_venda),
                        "data": str(data_venda)
                    }

                sucesso = False
                tentativas = 0
                while not sucesso and tentativas < 6:
                    try:
                        supabase.table("vendas").insert(payload_venda).execute()
                        sucesso = True
                    except Exception as err:
                        err_str = str(err)
                        # Remove a chave específica relatada pelo erro de schema cache
                        if "Could not find the '" in err_str and "' column" in err_str:
                            col_problem = err_str.split("Could not find the '")[1].split("' column")[0]
                            if col_problem in payload_venda:
                                del payload_venda[col_problem]
                        else:
                            st.error(f"Erro ao registrar a venda no banco de dados: {err}")
                            break
                        tentativas += 1

                if sucesso:
                    if dt_receb_str and valor_venda > 0:
                        supabase.table("caixa").insert({
                            "data": dt_receb_str,
                            "desc": f"Venda {codigo_sel} ({qtd_venda}un) - {cliente.strip()}",
                            "tipo": "Venda",
                            "valor": float(valor_venda)
                        }).execute()
                        
                    st.session_state["flash_success"] = f"🎉 Venda salva com sucesso!"
                    st.rerun()

    st.markdown("---")
    st.subheader("⏳ Vendas Pendentes de Recebimento")
    if not df_vendas.empty:
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_vendas.columns else ("data_receb" if "data_receb" in df_vendas.columns else None)
        if col_dt_rec:
            df_pendentes = df_vendas[df_vendas[col_dt_rec].isna() | (df_vendas[col_dt_rec] == "") | (df_vendas[col_dt_rec] == "None")].copy()
        else:
            df_pendentes = pd.DataFrame()

        if not df_pendentes.empty:
            opts_pend = [f"ID {r['id']} | {r.get('cliente','')} - R$ {r.get('valor',0.0):,.2f} (Venda: {format_data_br(r.get('data',''))})" for _, r in df_pendentes.iterrows()]
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
                    
                    c_cod = "codigo" if "codigo" in row_v else ("codigo_produto" if "codigo_produto" in row_v else "cod_produto")
                    
                    if float(row_v.get("valor", 0)) > 0:
                        supabase.table("caixa").insert({
                            "data": str(dt_confirmada),
                            "desc": f"Venda {row_v.get(c_cod,'')} ({row_v.get('qtd',1)}un) - {row_v.get('cliente','')}",
                            "tipo": "Venda",
                            "valor": float(row_v.get("valor", 0))
                        }).execute()
                    
                    st.success("🎉 Recebimento confirmado e lançado no caixa!")
                    st.rerun()

            with c_rec3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Excluir Venda Incorreta", use_container_width=True, type="secondary"):
                    venda_id = int(venda_sel.split("|")[0].replace("ID", "").strip())
                    supabase.table("vendas").delete().eq("id", venda_id).execute()
                    st.success("🗑️ Venda excluída com sucesso!")
                    st.rerun()

            df_pend_exib = df_pendentes.copy()
            if "data" in df_pend_exib.columns:
                df_pend_exib["data"] = df_pend_exib["data"].apply(format_data_br)
            cols_pend_exibir = [col for col in df_pend_exib.columns if col not in ["created_at"]]
            st.dataframe(df_pend_exib[cols_pend_exibir], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma venda pendente de recebimento no momento.")
    else:
        st.info("Nenhuma venda registrada.")

    st.markdown("---")
    st.subheader("📋 Histórico Detalhado de Vendas")
    if not df_vendas.empty:
        col1_hist, col2_hist = st.columns([3, 1])
        with col2_hist:
            venda_excluir_hist = st.selectbox("Selecione Venda do Histórico para Excluir:", [f"ID {r['id']} | {r.get('cliente','')} - R$ {r.get('valor',0.0):,.2f}" for _, r in df_vendas.iterrows()])
            if st.button("🗑️ Excluir Venda Selecionada", use_container_width=True):
                v_id_excluir = int(venda_excluir_hist.split("|")[0].replace("ID", "").strip())
                supabase.table("vendas").delete().eq("id", v_id_excluir).execute()
                st.success("🗑️ Venda removida com sucesso!")
                st.rerun()

        df_v_exib = df_vendas.copy()
        for c_dt in ["data", "data_venda", "data_recebimento", "data_receb"]:
            if c_dt in df_v_exib.columns:
                df_v_exib[c_dt] = df_v_exib[c_dt].apply(format_data_br)

        st.dataframe(df_v_exib, use_container_width=True, hide_index=True)

elif menu == "🛍️ Compras":
    st.subheader("🛍️ Cadastrar Nova Compra de Mercadoria")
    
    opcoes_prod = ["➕ [NOVO] Cadastrar Novo Produto"]
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        for _, r in df_produtos.iterrows():
            cod = r.get('codigo', '')
            frase = r.get('frase', '')
            cor = r.get('cor', '')
            cor_e = r.get('cor_estampa', '')
            cat = r.get('categoria', '')
            opcoes_prod.append(f"✏️ [{cod}] | {frase} - {cor} - {cor_e} - {cat}")
    
    item_selecionado = st.selectbox(
        "📌 Selecione um Item para Editar/Excluir ou Cadastre um Novo (Pesquise por código, frase, cor ou categoria):", 
        opcoes_prod,
        help="Digite na caixa de texto para buscar por qualquer característica do produto."
    )
    
    dados_item = {}
    is_edicao = False
    if item_selecionado and not item_selecionado.startswith("➕"):
        is_edicao = True
        cod_existente = item_selecionado.split("]")[0].replace("✏️ [", "").strip()
        row_match = df_produtos[df_produtos["codigo"] == cod_existente]
        if not row_match.empty:
            dados_item = row_match.iloc[0].to_dict()

    col_qtd_nome = "qtd_estoque" if "qtd_estoque" in dados_item else ("qtd" if "qtd" in dados_item else "estoque")

    with st.form("form_compra"):
        c1, c2, c3 = st.columns(3)
        with c1:
            cod_c = st.text_input("Código (ex: BL-0001) *", value=str(dados_item.get("codigo", "")), disabled=is_edicao)
            cor_c = st.text_input("Cor do Boné *", value=str(dados_item.get("cor", "")))
        with c2:
            frase_c = st.text_input("Arte Estampada *", value=str(dados_item.get("frase", "")))
            cor_estampa_c = st.text_input("Cor Estampada *", value=str(dados_item.get("cor_estampa", "")))
        with c3:
            cat_opts = ["Básico", "Kids", "Outro", "Premium"]
            cat_val = str(dados_item.get("categoria", "Básico"))
            idx_cat = cat_opts.index(cat_val) if cat_val in cat_opts else 0
            cat_c = st.selectbox("Produto", cat_opts, index=idx_cat)
            custo_c = st.number_input("Custo Unitário (R$) *", min_value=0.0, value=float(dados_item.get("custo", 29.0)))

        c4 = st.container()
        with c4:
            dt_aquisicao = st.date_input("Data da Aquisição *", datetime.date.today(), format="DD/MM/YYYY")

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            btn_salvar = st.form_submit_button("💾 Salvar / Atualizar Item", use_container_width=True, type="primary")
        with b_col2:
            btn_excluir = st.form_submit_button("🗑️ Excluir Item Cadastrado", use_container_width=True)

        if btn_salvar:
            if not cod_c.strip():
                st.error("Informe o código do produto!")
            else:
                novo_prod = {
                    "codigo": cod_c.strip(),
                    "cor": cor_c.strip(),
                    "frase": frase_c.strip(),
                    "cor_estampa": cor_estampa_c.strip(),
                    "categoria": cat_c,
                    "custo": float(custo_c),
                    col_qtd_nome: 1
                }
                supabase.table("produtos").upsert(novo_prod, on_conflict="codigo").execute()
                
                if not is_edicao:
                    custo_total = float(custo_c)
                    if custo_total > 0:
                        supabase.table("caixa").insert({
                            "data": str(dt_aquisicao),
                            "desc": "Compra de Mercadorias (Estoque)",
                            "tipo": "Compra de Mercadorias",
                            "valor": custo_total
                        }).execute()

                st.session_state["flash_success"] = f"🎉 Produto {cod_c} salvo com sucesso!"
                st.rerun()

        if btn_excluir:
            if not is_edicao:
                st.error("Selecione um produto existente para excluir!")
            else:
                supabase.table("produtos").delete().eq("codigo", cod_c.strip()).execute()
                st.session_state["flash_success"] = f"🗑️ Produto {cod_c} excluído com sucesso!"
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Histórico Permanente de Aquisições")
    if not df_produtos.empty:
        mapa_colunas = {
            "codigo": "Código",
            "cor": "Cor do Boné",
            "frase": "Arte Estampada",
            "cor_estampa": "Cor Estampada",
            "categoria": "Produto",
            "custo": "Custo",
            "qtd_estoque": "Estoque",
            "qtd": "Estoque",
            "estoque": "Estoque"
        }
        
        cols_exibir = [col for col in df_produtos.columns if col not in ["id", "created_at"]]
        df_exibicao = df_produtos[cols_exibir].rename(columns=mapa_colunas)
        
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

elif menu == "📦 Estoque":
    st.subheader("📦 Estoque Atual em Tempo Real (Saldo Disponível)")
    
    if not df_produtos.empty:
        df_est = df_produtos.copy()
        df_est["Status"] = "Disponível"
        
        with st.expander("🔍 Consultar e Pesquisar no Estoque", expanded=False):
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                busca_texto = st.text_input("Pesquisar por Código ou Arte:")
            with c_f2:
                cat_unicas = ["Todas"] + sorted(list(df_est["categoria"].dropna().unique())) if "categoria" in df_est.columns else ["Todas"]
                filtro_cat = st.selectbox("Filtrar por Produto/Categoria:", cat_unicas)
            with c_f3:
                cor_unicas = ["Todas"] + sorted(list(df_est["cor"].dropna().unique())) if "cor" in df_est.columns else ["Todas"]
                filtro_cor = st.selectbox("Filtrar por Cor do Boné:", cor_unicas)

            if busca_texto:
                df_est = df_est[
                    df_est["codigo"].astype(str).str.contains(busca_texto, case=False, na=False) |
                    df_est.get("frase", pd.Series([""]*len(df_est))).astype(str).str.contains(busca_texto, case=False, na=False)
                ]
            if filtro_cat != "Todas" and "categoria" in df_est.columns:
                df_est = df_est[df_est["categoria"] == filtro_cat]
            if filtro_cor != "Todas" and "cor" in df_est.columns:
                df_est = df_est[df_est["cor"] == filtro_cor]

        mapa_colunas_est = {
            "codigo": "Código",
            "cor": "Cor do Boné",
            "frase": "Arte Estampada",
            "cor_estampa": "Cor Estampada",
            "categoria": "Produto",
            "custo": "Custo",
            "qtd_estoque": "Estoque",
            "qtd": "Estoque",
            "estoque": "Estoque"
        }
        cols_est = [col for col in df_est.columns if col not in ["id", "created_at"]]
        st.dataframe(df_est[cols_est].rename(columns=mapa_colunas_est), use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif menu == "💵 Custos":
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷️ Custos de Venda", "🎪 Feiras"], horizontal=True)

    if sub_tab == "📦 Mercadorias":
        if not df_produtos.empty:
            df_m = df_produtos.copy()
            col_custo = "custo" if "custo" in df_m.columns else None
            col_qtd = "qtd" if "qtd" in df_m.columns else ("estoque" if "estoque" in df_m.columns else ("qtd_estoque" if "qtd_estoque" in df_m.columns else None))

            if col_custo and col_qtd:
                df_m["custo_num"] = pd.to_numeric(df_m[col_custo], errors="coerce").fillna(0)
                df_m["qtd_num"] = pd.to_numeric(df_m[col_qtd], errors="coerce").fillna(0)
                df_m["Custo Total"] = df_m["custo_num"] * df_m["qtd_num"]
                cols_para_exibir = [c for c in ["codigo", "categoria", col_qtd, col_custo, "Custo Total"] if c in df_m.columns]
                
                mapa_colunas_custos = {
                    "codigo": "Código",
                    "categoria": "Produto",
                    col_qtd: "Estoque",
                    "custo": "Custo"
                }
                st.dataframe(df_m[cols_para_exibir].rename(columns=mapa_colunas_custos), use_container_width=True, hide_index=True)
            else:
                cols_m = [col for col in df_m.columns if col not in ["id", "created_at"]]
                st.dataframe(df_m[cols_m], use_container_width=True, hide_index=True)

    elif sub_tab == "🏷️ Custos de Venda":
        with st.form("form_cv"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cv = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
                desc_cv = st.text_input("Descrição *")
            with c2:
                tipo_cv = st.selectbox("Tipo de Despesa *", ["Brindes", "Embalagem", "Unboxing"])
            with c3:
                val_cv = st.number_input("Valor (R$) *", min_value=0.01, value=10.0)

            if st.form_submit_button("Adicionar Custo de Venda", use_container_width=True):
                raw_c_dict = {
                    "subcategoria": "Custos de Venda",
                    "data": str(dt_cv),
                    "desc": desc_cv.strip(),
                    "descricao": desc_cv.strip(),
                    "tipo": tipo_cv,
                    "valor": float(val_cv)
                }

                cols_custos = df_custos.columns.tolist() if not df_custos.empty else []
                if cols_custos:
                    c_dict = {k: v for k, v in raw_c_dict.items() if k in cols_custos}
                else:
                    c_dict = {"subcategoria": "Custos de Venda", "data": str(dt_cv), "desc": desc_cv.strip(), "tipo": tipo_cv, "valor": float(val_cv)}

                try:
                    supabase.table("custos_avulsos").insert(c_dict).execute()
                    supabase.table("caixa").insert({"data": str(dt_cv), "desc": f"[Custos de Venda] {desc_cv.strip()}", "tipo": tipo_cv, "valor": float(val_cv)}).execute()
                    st.session_state["flash_success"] = "Custo registrado com sucesso!"
                    st.rerun()
                except Exception as err_c:
                    st.error(f"Erro ao registrar custo no banco de dados: {err_c}")

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
                val_cf = st.number_input("Valor (R$) *", min_value=0.01, value=50.0)

            if st.form_submit_button("Adicionar Custo de Feira", use_container_width=True):
                raw_cf_dict = {
                    "subcategoria": "Feiras",
                    "data": str(dt_cf),
                    "nomeFeira": feira_cf.strip(),
                    "desc": desc_cf.strip(),
                    "descricao": desc_cf.strip(),
                    "tipo": tipo_cf,
                    "valor": float(val_cf)
                }

                cols_custos = df_custos.columns.tolist() if not df_custos.empty else []
                if cols_custos:
                    cf_dict = {k: v for k, v in raw_cf_dict.items() if k in cols_custos}
                else:
                    cf_dict = {"subcategoria": "Feiras", "data": str(dt_cf), "nomeFeira": feira_cf.strip(), "desc": desc_cf.strip(), "tipo": tipo_cf, "valor": float(val_cf)}

                try:
                    supabase.table("custos_avulsos").insert(cf_dict).execute()
                    supabase.table("caixa").insert({"data": str(dt_cf), "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}", "tipo": tipo_cf, "valor": float(val_cf)}).execute()
                    st.session_state["flash_success"] = "Custo de feira registrado com sucesso!"
                    st.rerun()
                except Exception as err_cf:
                    st.error(f"Erro ao registrar custo de feira: {err_cf}")

elif menu == "🤝 Aportes dos Sócios":
    st.subheader("🤝 Registro de Aportes e Devoluções")
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_ap = st.date_input("Data *", datetime.date.today(), format="DD/MM/YYYY")
    with c2:
        socio_ap = st.selectbox("Sócio *", ["Renan", "Ronald"])
    with c3:
        val_ap = st.number_input("Valor (R$) *", min_value=1.0, value=100.0)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🤝 Registrar Aporte", use_container_width=True, type="primary"):
            supabase.table("aportes").insert({"data": str(dt_ap), "socio": socio_ap, "valor": float(val_ap), "tipo": "Aporte"}).execute()
            supabase.table("caixa").insert({"data": str(dt_ap), "desc": f"Aporte ({socio_ap})", "tipo": "Aporte de Sócio", "valor": float(val_ap)}).execute()
            st.session_state["flash_success"] = f"Aporte registrado!"
            st.rerun()

    with col_btn2:
        if st.button("🔄 Devolução de Aporte", use_container_width=True):
            supabase.table("aportes").insert({"data": str(dt_ap), "socio": socio_ap, "valor": float(val_ap), "tipo": "Devolução"}).execute()
            supabase.table("caixa").insert({"data": str(dt_ap), "desc": f"Devolução ({socio_ap})", "tipo": "Devolução de Aporte", "valor": float(val_ap)}).execute()
            st.session_state["flash_success"] = f"Devolução registrada!"
            st.rerun()

elif menu == "💰 Fluxo de Caixa":
    st.subheader("💰 Extrato Consolidado de Caixa")
    if not df_caixa.empty:
        df_caixa_exib = df_caixa.copy()
        if "data" in df_caixa_exib.columns:
            df_caixa_exib["data"] = df_caixa_exib["data"].apply(format_data_br)
        cols_caixa = [col for col in df_caixa_exib.columns if col not in ["id", "created_at"]]
        st.dataframe(df_caixa_exib[cols_caixa], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação no caixa.")

elif menu == "📥 Importação":
    st.subheader("📥 Importação de Dados em Lote")
    st.markdown("Selecione o tipo de dado que deseja importar e envie o arquivo Excel (.xlsx) ou CSV (.csv).")

    tipo_import = st.selectbox("Escolha o destino dos dados *", ["🛍️ Compras (Produtos)", "🛒 Vendas"])

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
