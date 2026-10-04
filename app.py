import datetime
import base64
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

    /* Container para Logomarca Expandida (Substitui o Cabeçalho) */
    .banner-logo-full {
        width: 100%;
        border-radius: 16px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.12);
        margin-bottom: 25px;
        object-fit: cover;
        display: block;
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

# Carregar dados
df_produtos = fetch_data("produtos")
df_vendas = fetch_data("vendas")
df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")

# Gestão da Logomarca Persistente na Sessão
if "logo_b64" not in st.session_state:
    st.session_state["logo_b64"] = None
if "logo_mime" not in st.session_state:
    st.session_state["logo_mime"] = "image/png"

# 3. Sidebar (Barra Lateral Esquerda) Ocultável
with st.sidebar:
    st.markdown("### 📌 Módulos do Sistema")
    menu = st.radio(
        "Navegue entre os módulos:",
        ["📈 Dashboard", "🛒 Vendas", "🛍️️ Compras", "📦 Estoque", "💵 Custos", "🤝 Aportes dos Sócios", "💰 Fluxo de Caixa"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    
    # Personalização da Logomarca
    with st.expander("🎨 Personalização", expanded=False):
        uploaded_logo = st.file_uploader(
            "Carregar Nova Logo da Marca", 
            type=["png", "jpg", "jpeg", "svg"],
            help="Envie a logomarca para substituir todo o cabeçalho principal."
        )
        if uploaded_logo is not None:
            bytes_data = uploaded_logo.getvalue()
            st.session_state["logo_b64"] = base64.b64encode(bytes_data).decode("utf-8")
            st.session_state["logo_mime"] = uploaded_logo.type
            st.success("Logo salva e fixada com sucesso!")
            st.rerun()

        if st.session_state["logo_b64"] is not None:
            if st.button("🗑️ Excluir Logo Atual", use_container_width=True, type="secondary"):
                st.session_state["logo_b64"] = None
                st.success("Logo removida com sucesso!")
                st.rerun()

# 4. Cabeçalho Principal: Substitui toda a área escura pela logo se enviada
if st.session_state["logo_b64"] is not None:
    logo_src = f"data:{st.session_state['logo_mime']};base64,{st.session_state['logo_b64']}"
    st.markdown(f'<img src="{logo_src}" class="banner-logo-full">', unsafe_allow_html=True)
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
    
    total_faturado = float(df_vendas["valor"].sum()) if not df_vendas.empty and "valor" in df_vendas.columns else 0.0
    total_cmv = float(df_vendas["custo"].sum()) if not df_vendas.empty and "custo" in df_vendas.columns else 0.0

    saldo_caixa = 0.0
    if not df_caixa.empty and "valor" in df_caixa.columns and "tipo" in df_caixa.columns:
        entradas = df_caixa[df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saidas = df_caixa[~df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saldo_caixa = float(entradas - saidas)

    total_estoque_qtd = 0
    if not df_produtos.empty:
        col_qtd_p = "qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else None)
        if col_qtd_p:
            total_estoque_qtd = int(pd.to_numeric(df_produtos[col_qtd_p], errors="coerce").fillna(0).sum())

    # Cards de KPIs
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ️</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV Total <span class="tooltip-icon" title="Custo das mercadorias vendidas nos bonés faturados">ℹ️️</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo financeiro líquido acumulado">ℹ️</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Itens no Estoque <span class="tooltip-icon" title="Quantidade total de bonés disponíveis no estoque">ℹ️</span></div><div class="kpi-value">{total_estoque_qtd} un</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    meses_disponiveis = ["TODOS"]
    if not df_vendas.empty and "data" in df_vendas.columns:
        df_vendas["mes_ano"] = df_vendas["data"].astype(str).str.slice(0, 7)
        meses_disponiveis.extend(sorted(df_vendas["mes_ano"].unique().tolist()))
    
    mes_sel = st.selectbox("📅 Selecionar Período / Mês:", list(set(meses_disponiveis)))
    
    df_vendas_fil = df_vendas.copy()
    if mes_sel != "TODOS" and not df_vendas_fil.empty:
        df_vendas_fil = df_vendas_fil[df_vendas_fil["data"].astype(str).str.startswith(mes_sel)]
        
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### 🟢 Faturamento vs. 🔴 CMV")
        if not df_vendas_fil.empty and "data" in df_vendas_fil.columns:
            df_vendas_fil["mes"] = df_vendas_fil["data"].astype(str).str.slice(0, 7)
            agrup = df_vendas_fil.groupby("mes")[["valor", "custo"]].sum().reset_index()
            fig1 = px.bar(agrup, x="mes", y=["valor", "custo"], barmode="group",
                          color_discrete_sequence=["#10b981", "#ef4444"], template="plotly_white")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Sem dados suficientes para gerar o gráfico.")

    with g2:
        st.markdown("#### 🎨 Cores Mais Vendidas")
        if not df_vendas_fil.empty and "codigo" in df_vendas_fil.columns and not df_produtos.empty:
            df_m = df_vendas_fil.merge(df_produtos, on="codigo", how="left")
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

elif menu == "🛒 Vendas":
    st.subheader("🛒 Lançar Nova Venda")
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        c_qtd_p = "qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else None)
        opts = [f"[{r['codigo']}] \"{r.get('frase','')}\" (Disponível: {r.get(c_qtd_p, 0) if c_qtd_p else 0} un)" for _, r in df_produtos.iterrows()]
        prod_sel = st.selectbox("🔍 Selecionar Boné do Estoque *", opts)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""
            qtd_venda = st.number_input("Quantidade *", min_value=1, value=1, step=1)
            cliente = st.text_input("Nome do Cliente *")
        with c2:
            valor_venda = st.number_input("Valor Total (R$) *", min_value=0.0, value=60.0, step=5.0)
            forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])
        with c3:
            data_venda = st.date_input("Data da Venda *", datetime.date.today())
            data_receb = st.date_input("Data de Recebimento (Opcional)", value=None)

        if st.button("🚀 Finalizar Venda", type="primary", use_container_width=True):
            if not cliente.strip():
                st.error("Informe o nome do cliente!")
            else:
                p_info = df_produtos[df_produtos["codigo"] == codigo_sel].iloc[0]
                custo_unit = float(p_info.get("custo", 0.0))
                
                nova_venda = {
                    "codigo": codigo_sel,
                    "qtd": int(qtd_venda),
                    "cliente": cliente.strip(),
                    "valor": float(valor_venda),
                    "pagto": forma_pagto,
                    "data": str(data_venda),
                    "data_recebimento": str(data_receb) if data_receb else None,
                    "custo": float(custo_unit * qtd_venda)
                }
                supabase.table("vendas").insert(nova_venda).execute()
                
                if data_receb and valor_venda > 0:
                    supabase.table("caixa").insert({
                        "data": str(data_receb),
                        "desc": f"Venda {codigo_sel} ({qtd_venda}un) - {cliente.strip()}",
                        "tipo": "Venda",
                        "valor": float(valor_venda)
                    }).execute()
                    
                st.session_state["flash_success"] = f"🎉 Venda salva com sucesso!"
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Histórico Detalhado de Vendas")
    if not df_vendas.empty:
        st.dataframe(df_vendas, use_container_width=True, hide_index=True)

elif menu == "🛍️ Compras":
    st.subheader("🛍️ Cadastrar Nova Compra de Mercadoria")
    with st.form("form_compra"):
        c1, c2, c3 = st.columns(3)
        with c1:
            cod_c = st.text_input("Código (ex: BL-0001) *")
            cor_c = st.text_input("Cor *")
        with c2:
            frase_c = st.text_input("Frase Estampada *")
            cat_c = st.selectbox("Categoria", ["Liso", "Premium"])
        with c3:
            custo_c = st.number_input("Custo Unitário (R$) *", min_value=0.0, value=29.0)
            qtd_c = st.number_input("Qtd Comprada *", min_value=1, value=1)
            dt_aquisicao = st.date_input("Data da Aquisição *", datetime.date.today())

        btn_compra = st.form_submit_button("➕ Adicionar / Atualizar Compra", use_container_width=True)
        if btn_compra:
            if not cod_c.strip():
                st.error("Informe o código do produto!")
            else:
                novo_prod = {
                    "codigo": cod_c.strip(),
                    "cor": cor_c.strip(),
                    "frase": frase_c.strip(),
                    "categoria": cat_c,
                    "custo": float(custo_c),
                    "qtd": int(qtd_c),
                    "dataAquisicao": str(dt_aquisicao)
                }
                supabase.table("produtos").upsert(novo_prod, on_conflict="codigo").execute()
                
                custo_total = float(custo_c * qtd_c)
                if custo_total > 0:
                    supabase.table("caixa").insert({
                        "data": str(dt_aquisicao),
                        "desc": "Compra de Mercadorias (Estoque)",
                        "tipo": "Compra de Mercadorias",
                        "valor": custo_total
                    }).execute()

                st.session_state["flash_success"] = f"🎉 Compra do produto {cod_c} registrada!"
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Histórico Permanente de Aquisições")
    if not df_produtos.empty:
        st.dataframe(df_produtos, use_container_width=True, hide_index=True)

elif menu == "📦 Estoque":
    st.subheader("📦 Estoque Atual em Tempo Real (Saldo Disponível)")
    if not df_produtos.empty:
        df_est = df_produtos.copy()
        df_est["Status"] = "Disponível"
        st.dataframe(df_est, use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif menu == "💵 Custos":
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷️ Custos de Venda", "🎪 Feiras"], horizontal=True)

    if sub_tab == "📦 Mercadorias":
        if not df_produtos.empty:
            df_m = df_produtos.copy()
            col_custo = "custo" if "custo" in df_m.columns else None
            col_qtd = "qtd" if "qtd" in df_m.columns else ("estoque" if "estoque" in df_m.columns else None)

            if col_custo and col_qtd:
                df_m["custo_num"] = pd.to_numeric(df_m[col_custo], errors="coerce").fillna(0)
                df_m["qtd_num"] = pd.to_numeric(df_m[col_qtd], errors="coerce").fillna(0)
                df_m["Custo Total"] = df_m["custo_num"] * df_m["qtd_num"]
                cols_para_exibir = [c for c in ["dataAquisicao", "categoria", col_qtd, col_custo, "Custo Total"] if c in df_m.columns]
                st.dataframe(df_m[cols_para_exibir], use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_m, use_container_width=True, hide_index=True)

    elif sub_tab == "🏷️ Custos de Venda":
        with st.form("form_cv"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cv = st.date_input("Data *", datetime.date.today())
                desc_cv = st.text_input("Descrição *")
            with c2:
                tipo_cv = st.selectbox("Tipo de Despesa *", ["Brindes", "Embalagem", "Unboxing"])
            with c3:
                val_cv = st.number_input("Valor (R$) *", min_value=0.01, value=10.0)

            if st.form_submit_button("Adicionar Custo de Venda", use_container_width=True):
                c_dict = {"subcategoria": "Custos de Venda", "data": str(dt_cv), "desc": desc_cv.strip(), "tipo": tipo_cv, "valor": float(val_cv)}
                supabase.table("custos_avulsos").insert(c_dict).execute()
                supabase.table("caixa").insert({"data": str(dt_cv), "desc": f"[Custos de Venda] {desc_cv.strip()}", "tipo": tipo_cv, "valor": float(val_cv)}).execute()
                st.session_state["flash_success"] = "Custo registrado!"
                st.rerun()

    elif sub_tab == "🎪 Feiras":
        with st.form("form_cf"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cf = st.date_input("Data *", datetime.date.today())
                feira_cf = st.text_input("Nome da Feira *")
            with c2:
                desc_cf = st.text_input("Descrição *")
                tipo_cf = st.selectbox("Tipo de Despesa *", ["Alimentação", "Decoração", "Instalação", "Taxa de Inscrição", "Transporte"])
            with c3:
                val_cf = st.number_input("Valor (R$) *", min_value=0.01, value=50.0)

            if st.form_submit_button("Adicionar Custo de Feira", use_container_width=True):
                c_dict = {"subcategoria": "Feiras", "data": str(dt_cf), "nomeFeira": feira_cf.strip(), "desc": desc_cf.strip(), "tipo": tipo_cf, "valor": float(val_cf)}
                supabase.table("custos_avulsos").insert(c_dict).execute()
                supabase.table("caixa").insert({"data": str(dt_cf), "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}", "tipo": tipo_cf, "valor": float(val_cf)}).execute()
                st.session_state["flash_success"] = "Custo de feira registrado!"
                st.rerun()

elif menu == "🤝 Aportes dos Sócios":
    st.subheader("🤝 Registro de Aportes e Devoluções")
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_ap = st.date_input("Data *", datetime.date.today())
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
        st.dataframe(df_caixa, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação no caixa.")
