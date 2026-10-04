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

def safe_insert(table_name: str, payload: dict):
    if not supabase:
        return False
    try:
        supabase.table(table_name).insert(payload).execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "Could not find the '" in err_str and "' column" in err_str:
            col_err = err_str.split("Could not find the '")[1].split("' column")[0]
            if col_err in payload:
                del payload[col_err]
                return safe_insert(table_name, payload)
        elif "PGRST205" in err_str or "schema cache" in err_str:
            return True
        st.error(f"Erro ao gravar na tabela `{table_name}`: {err}")
        return False

def safe_upsert_produto(payload: dict):
    if not supabase:
        return False
    try:
        supabase.table("produtos").upsert(payload, on_conflict="codigo").execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "Could not find the 'data_aquisicao'" in err_str or "PGRST204" in err_str:
            if "data_aquisicao" in payload:
                del payload["data_aquisicao"]
            try:
                supabase.table("produtos").upsert(payload, on_conflict="codigo").execute()
                return True
            except Exception as inner_err:
                st.error(f"Erro ao salvar produto: {inner_err}")
                return False
        st.error(f"Erro ao atualizar o produto: {err}")
        return False

def estornar_estoque(codigo_prod, qtd_estorno):
    if not supabase or not codigo_prod or qtd_estorno <= 0:
        return
    try:
        res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
        if res_p.data and len(res_p.data) > 0:
            prod_row = res_p.data[0]
            col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else ("estoque" if "estoque" in prod_row else "qtd_estoque"))
            qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce"))
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
        st.error(f"Erro ao salvar no Supabase: {e}")
        return False

def delete_logo_from_db():
    if not supabase:
        return
    try:
        supabase.table("configuracoes").delete().eq("chave", "logo_header").execute()
        get_saved_logo.clear()
    except Exception as e:
        st.error(f"Erro ao remover no Supabase: {e}")

# Carregar tabelas
df_produtos = fetch_data("produtos")
df_vendas = fetch_data("vendas")
df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")

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
        ["📈 Dashboard", "🛍️ Compras", "📦 Estoque", "🛒 Vendas", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "📥 Importação", "💾 Gestão de Dados"],
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
            if st.button("🗑️ Excluir Logo Atual", use_container_width=True, type="secondary"):
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
    total_cmv = float(df_vendas["custo"].sum()) if not df_vendas.empty and "custo" in df_vendas.columns else 0.0

    saldo_caixa = 0.0
    if not df_caixa.empty and "valor" in df_caixa.columns and "tipo" in df_caixa.columns:
        entradas = df_caixa[df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saidas = df_caixa[~df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])]["valor"].sum()
        saldo_caixa = float(entradas - saidas)

    total_estoque_qtd = 0
    if not df_produtos.empty:
        col_qtd_p = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else None))
        if col_qtd_p:
            total_estoque_qtd = int(pd.to_numeric(df_produtos[col_qtd_p], errors="coerce").fillna(0).sum())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV Total <span class="tooltip-icon" title="Custo das mercadorias vendidas nos bonés faturados">ℹ️</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo financeiro líquido acumulado">ℹ</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
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

elif menu == "🛒 Vendas":
    st.subheader("🛒 Lançar Nova Venda")
    if not df_produtos.empty and "codigo" in df_produtos.columns:
        c_qtd_p = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else "qtd_estoque"))
        
        df_prod_disp = df_produtos[pd.to_numeric(df_produtos.get(c_qtd_p, 0), errors="coerce").fillna(0) > 0].copy()
        
        if not df_prod_disp.empty:
            busca_bone = st.text_input("🔍 Pesquisar Boné no Estoque (por código, frase ou cor):", "")
            if busca_bone.strip():
                df_prod_disp = df_prod_disp[
                    df_prod_disp["codigo"].astype(str).str.contains(busca_bone, case=False, na=False) |
                    df_prod_disp.get("frase", pd.Series([""]*len(df_prod_disp))).astype(str).str.contains(busca_bone, case=False, na=False) |
                    df_prod_disp.get("cor", pd.Series([""]*len(df_prod_disp))).astype(str).str.contains(busca_bone, case=False, na=False)
                ]

            if not df_prod_disp.empty:
                opts = [f"[{r['codigo']}] \"{r.get('frase','')}\" (Disponível: {r.get(c_qtd_p, 0)} un)" for _, r in df_prod_disp.iterrows()]
                prod_sel = st.selectbox("Selecione o Boné Encontrado *", opts)
                
                codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""
                
                p_match = df_prod_disp[df_prod_disp["codigo"] == codigo_sel]
                estoque_disp = int(pd.to_numeric(p_match.iloc[0].get(c_qtd_p, 1), errors="coerce")) if not p_match.empty else 1
                max_qtd = max(1, estoque_disp)

                c1, c2, c3 = st.columns(3)
                with c1:
                    qtd_venda = st.number_input("Quantidade *", min_value=1, max_value=max_qtd, value=1, step=1, help=f"Quantidade disponível em estoque: {max_qtd}")
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
                        custo_unit = float(p_info.get("custo", 0.0))
                        dt_receb_str = str(data_receb) if data_receb is not None else None

                        val_venda_fmt = round(float(valor_venda), 2)
                        custo_calc_fmt = round(float(custo_unit * qtd_venda), 2)

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
                            "custo_unitario": round(float(custo_unit), 2)
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
            st.warning("Nenhum produto disponível em estoque no momento.")

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
                if st.button("🗑️ Excluir Venda Incorreta", use_container_width=True, type="secondary"):
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
                "Valor": df_pend_exib.get(col_val, 0.0).apply(lambda v: f"R$ {float(v):,.2f}"),
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
            c_val_exib = float(row.get(col_val, 0.0))
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

    col_qtd_nome = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else ("estoque" if "estoque" in df_produtos.columns else "qtd_estoque"))

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
            custo_c = st.number_input("Custo Unitário (R$) *", min_value=0.0, value=float(dados_item.get("custo", 29.0)), format="%.2f")

        c_extra1, c_extra2 = st.columns(2)
        with c_extra1:
            estampa_extra = st.number_input("Estampa Extra (R$)", min_value=0.0, value=float(dados_item.get("estampa_extra", 0.0)), format="%.2f")
        with c_extra2:
            matriz_bordado = st.number_input("Matriz Bordado (R$)", min_value=0.0, value=float(dados_item.get("matriz_bordado", 0.0)), format="%.2f")

        c4_1, c4_2 = st.columns(2)
        with c4_1:
            qtd_comprada = st.number_input("Quantidade Comprada *", min_value=1, value=1, step=1)
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
                custo_prod_fmt = round(float(custo_c), 2)
                valor_compra_total = round(custo_prod_fmt * int(qtd_comprada), 2)
                
                estoque_atual = int(dados_item.get(col_qtd_nome, 0)) if is_edicao else 0
                novo_estoque_calculado = estoque_atual + int(qtd_comprada) if is_edicao else int(qtd_comprada)
                
                qtd_hist_comprada = int(dados_item.get("qtd_comprada", 0)) + int(qtd_comprada) if is_edicao else int(qtd_comprada)

                novo_prod = {
                    "codigo": cod_c.strip(),
                    "cor": cor_c.strip(),
                    "frase": frase_c.strip(),
                    "cor_estampa": cor_estampa_c.strip(),
                    "categoria": cat_c,
                    "custo": custo_prod_fmt,
                    "estampa_extra": round(float(estampa_extra), 2),
                    "matriz_bordado": round(float(matriz_bordado), 2),
                    col_qtd_nome: novo_estoque_calculado,
                    "qtd_comprada": qtd_hist_comprada,
                    "data_aquisicao": str(dt_aquisicao)
                }

                if safe_upsert_produto(novo_prod):
                    if valor_compra_total > 0:
                        safe_insert("caixa", {
                            "data": str(dt_aquisicao),
                            "desc": f"Compra de Mercadorias - {cod_c.strip()} ({qtd_comprada}un)",
                            "tipo": "Compra de Mercadorias",
                            "valor": valor_compra_total
                        })

                    st.session_state["flash_success"] = f"🎉 Produto {cod_c} salvo e estoque atualizado com sucesso!"
                    st.rerun()

        if btn_excluir:
            if not is_edicao:
                st.error("Selecione um produto existente para excluir!")
            else:
                try:
                    supabase.table("produtos").delete().eq("codigo", cod_c.strip()).execute()
                    st.session_state["flash_success"] = f"🗑️ Produto {cod_c} excluído com sucesso!"
                    st.rerun()
                except Exception as err_del:
                    st.error(f"Erro ao excluir o produto: {err_del}")

    st.markdown("---")
    st.subheader("📋 Histórico Permanente de Aquisições")
    
    if not df_produtos.empty:
        df_exib_compras = df_produtos.copy()
        
        if "custo" in df_exib_compras.columns:
            df_exib_compras["custo"] = df_exib_compras["custo"].apply(lambda v: f"R$ {float(v):,.2f}")

        mapa_colunas_compras = {
            "codigo": "Código",
            "cor": "Cor do Boné",
            "frase": "Arte Estampada",
            "cor_estampa": "Cor Estampada",
            "categoria": "Produto",
            "custo": "Custo Unitário"
        }
        
        cols_compras = [col for col in df_exib_compras.columns if col in mapa_colunas_compras]
        st.dataframe(df_exib_compras[cols_compras].rename(columns=mapa_colunas_compras), use_container_width=True, hide_index=True)

elif menu == "📦 Estoque":
    st.subheader("📦 Estoque Atual")
    
    if not df_produtos.empty:
        df_est = df_produtos.copy()
        col_qtd_est = "qtd_estoque" if "qtd_estoque" in df_est.columns else ("qtd" if "qtd" in df_est.columns else ("estoque" if "estoque" in df_est.columns else "qtd_estoque"))
        
        df_est["Status"] = df_est[col_qtd_est].apply(
            lambda val: "Disponível" if pd.to_numeric(val, errors="coerce") > 0 else "Indisponível"
        )
        
        df_est_disponivel = df_est[df_est["Status"] == "Disponível"].copy()
        
        if not df_est_disponivel.empty:
            with st.expander("🔍 Consultar e Pesquisar no Estoque", expanded=False):
                c_f1, c_f2, c_f3 = st.columns(3)
                with c_f1:
                    busca_texto = st.text_input("Pesquisar por Código ou Arte:")
                with c_f2:
                    cat_unicas = ["Todas"] + sorted(list(df_est_disponivel["categoria"].dropna().unique())) if "categoria" in df_est_disponivel.columns else ["Todas"]
                    filtro_cat = st.selectbox("Filtrar por Produto/Categoria:", cat_unicas)
                with c_f3:
                    cor_unicas = ["Todas"] + sorted(list(df_est_disponivel["cor"].dropna().unique())) if "cor" in df_est_disponivel.columns else ["Todas"]
                    filtro_cor = st.selectbox("Filtrar por Cor do Boné:", cor_unicas)

                if busca_texto:
                    df_est_disponivel = df_est_disponivel[
                        df_est_disponivel["codigo"].astype(str).str.contains(busca_texto, case=False, na=False) |
                        df_est_disponivel.get("frase", pd.Series([""]*len(df_est_disponivel))).astype(str).str.contains(busca_texto, case=False, na=False)
                    ]
                if filtro_cat != "Todas" and "categoria" in df_est_disponivel.columns:
                    df_est_disponivel = df_est_disponivel[df_est_disponivel["categoria"] == filtro_cat]
                if filtro_cor != "Todas" and "cor" in df_est_disponivel.columns:
                    df_est_disponivel = df_est_disponivel[df_est_disponivel["cor"] == filtro_cor]

            if "custo" in df_est_disponivel.columns:
                df_est_disponivel["custo"] = df_est_disponivel["custo"].apply(lambda v: f"R$ {float(v):,.2f}")

            mapa_colunas_est = {
                "codigo": "Código",
                "cor": "Cor do Boné",
                "frase": "Arte Estampada",
                "cor_estampa": "Cor Estampada",
                "categoria": "Produto",
                "custo": "Custo",
                col_qtd_est: "Estoque",
                "Status": "Status"
            }
            
            has_extra = "estampa_extra" in df_est_disponivel.columns and pd.to_numeric(df_est_disponivel["estampa_extra"], errors="coerce").fillna(0).sum() > 0
            has_matriz = "matriz_bordado" in df_est_disponivel.columns and pd.to_numeric(df_est_disponivel["matriz_bordado"], errors="coerce").fillna(0).sum() > 0

            cols_est = [col for col in [
                "codigo", "cor", "frase", "cor_estampa", "categoria", "custo", 
                "estampa_extra" if has_extra else None, 
                "matriz_bordado" if has_matriz else None, 
                col_qtd_est, "Status"
            ] if col is not None and col in df_est_disponivel.columns]

            if has_extra:
                mapa_colunas_est["estampa_extra"] = "Estampa Extra"
            if has_matriz:
                mapa_colunas_est["matriz_bordado"] = "Matriz Bordado"

            st.dataframe(df_est_disponivel[cols_est].rename(columns=mapa_colunas_est), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum item disponível em estoque no momento.")
    else:
        st.info("Estoque vazio no momento.")

elif menu == "💵 Custos":
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷️ Custos de Venda", "🎪 Feiras"], horizontal=True)

    if sub_tab == "📦 Mercadorias":
        if not df_produtos.empty:
            df_m = df_produtos.copy()
            col_custo = "custo" if "custo" in df_m.columns else "custo_unitario"
            col_data_aq = "data_aquisicao" if "data_aquisicao" in df_m.columns else "created_at"

            df_m["custo_num"] = pd.to_numeric(df_m[col_custo], errors="coerce").fillna(0.0)
            
            col_qtd_ref = "qtd_comprada" if "qtd_comprada" in df_m.columns else ("qtd_estoque" if "qtd_estoque" in df_m.columns else "qtd")
            df_m["qtd_num"] = pd.to_numeric(df_m[col_qtd_ref], errors="coerce").fillna(1)
            df_m["qtd_num"] = df_m["qtd_num"].apply(lambda v: max(1, int(v)))
            
            df_m["Custo Total Calc"] = df_m["custo_num"] * df_m["qtd_num"]
            df_m["Data_Formatada"] = df_m[col_data_aq].apply(format_data_br)

            st.markdown("##### 📊 Resumo Agrupado por Data da Aquisição")
            agrup_data = df_m.groupby("Data_Formatada").agg({
                "qtd_num": "sum",
                "Custo Total Calc": "sum"
            }).reset_index().rename(columns={"Data_Formatada": "Data da Aquisição", "qtd_num": "Quantidade Comprada"})

            agrup_data["Custo Total"] = agrup_data["Custo Total Calc"].apply(lambda v: f"R$ {float(v):,.2f}")
            st.dataframe(agrup_data[["Data da Aquisição", "Quantidade Comprada", "Custo Total"]], use_container_width=True, hide_index=True)

            with st.expander("🔍 Visualizar Registros Individuais de Compras", expanded=False):
                df_m["Custo Unitário"] = df_m["custo_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                df_m["Custo Total"] = df_m["Custo Total Calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                
                mapa_c_ind = {
                    "codigo": "Código",
                    "categoria": "Produto",
                    "Custo Unitário": "Custo Unitário",
                    "Custo Total": "Custo Total",
                    "Data_Formatada": "Data da Aquisição"
                }
                cols_ind = [c for c in ["codigo", "categoria", "Custo Unitário", "Custo Total", "Data_Formatada"] if c in df_m.columns]
                st.dataframe(df_m[cols_ind].rename(columns=mapa_c_ind), use_container_width=True, hide_index=True)

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
                
                safe_insert("custos_avulsos", payload_cv)
                safe_insert("caixa", {
                    "data": str(dt_cv), 
                    "desc": f"[Custos de Venda] {desc_cv.strip()}", 
                    "tipo": tipo_cv, 
                    "valor": val_cv_fmt
                })
                st.session_state["flash_success"] = "Custo de Venda registrado com sucesso!"
                st.rerun()

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
                
                safe_insert("custos_avulsos", payload_cf)
                safe_insert("caixa", {
                    "data": str(dt_cf), 
                    "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}", 
                    "tipo": tipo_cf, 
                    "valor": val_cf_fmt
                })
                st.session_state["flash_success"] = "Custo de Feira registrado com sucesso!"
                st.rerun()

# Módulo Aportes dos Sócios corrigido para evitar KeyError na coluna 'tipo'
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
                "valor": val_ap_fmt,
                "tipo": "Devolução"
            }
            if safe_insert("aportes", payload_dev):
                safe_insert("caixa", {
                    "data": str(dt_ap),
                    "desc": f"Devolução ({socio_ap})",
                    "tipo": "Devolução de Aporte",
                    "valor": val_ap_fmt
                })
                st.session_state["flash_success"] = f"Devolução de R$ {val_ap_fmt:,.2f} registrada com sucesso!"
                st.rerun()

    st.markdown("---")
    st.subheader("📊 Resumo Consolidado por Sócio")
    
    if not df_aportes.empty:
        df_ap_calc = df_aportes.copy()
        
        # Assegura a existência da coluna 'tipo' e 'socio' sem disparar KeyError
        if "tipo" not in df_ap_calc.columns:
            if "operacao" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["operacao"]
            elif "forma" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["forma"]
            else:
                df_ap_calc["tipo"] = "Aporte"
                
        if "socio" not in df_ap_calc.columns:
            df_ap_calc["socio"] = "Não informado"

        df_ap_calc["valor_num"] = pd.to_numeric(df_ap_calc.get("valor", 0), errors="coerce").fillna(0.0)
        
        resumo_socios = []
        for s in ["Renan", "Ronald"]:
            df_s = df_ap_calc[df_ap_calc["socio"].astype(str).str.lower() == s.lower()]
            
            ent = df_s[df_s["tipo"].astype(str).str.contains("Aporte", case=False, na=False)]["valor_num"].sum()
            sai = df_s[df_s["tipo"].astype(str).str.contains("Devoluc|Devoluç", case=False, na=False)]["valor_num"].sum()
            saldo_dev = ent - sai
            resumo_socios.append({
                "Sócio": s,
                "Total Aportado (R$)": f"R$ {ent:,.2f}",
                "Total Devolvido (R$)": f"R$ {sai:,.2f}",
                "Saldo a Devolver (R$)": f"R$ {saldo_dev:,.2f}"
            })
            
        st.dataframe(pd.DataFrame(resumo_socios), use_container_width=True, hide_index=True)

        st.markdown("##### 📋 Relatório Detalhado de Movimentações de Aportes")
        df_ap_exib = df_aportes.copy()
        
        col_dt_ap = "data" if "data" in df_ap_exib.columns else "created_at"
        df_ap_exib["Data_Formatada"] = df_ap_exib[col_dt_ap].apply(format_data_br) if col_dt_ap in df_ap_exib.columns else ""
        df_ap_exib["Valor (R$)"] = pd.to_numeric(df_ap_exib.get("valor", 0), errors="coerce").fillna(0.0).apply(lambda v: f"R$ {v:,.2f}")
        
        mapa_ap = {
            "Data_Formatada": "Data",
            "socio": "Sócio",
            "tipo": "Operação / Forma",
            "Valor (R$)": "Valor (R$)"
        }
        cols_ap_show = [c for c in ["Data_Formatada", "socio", "tipo", "Valor (R$)"] if c in df_ap_exib.columns]
        st.dataframe(df_ap_exib[cols_ap_show].rename(columns=mapa_ap), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum aporte ou devolução registrado no momento.")

# Módulo Fluxo de Caixa corrigido com ordenação homogênea de datas para evitar TypeError
elif menu == "💰 Fluxo de Caixa":
    st.subheader("💰 Extrato Consolidado de Caixa")
    
    lista_movimentos = []

    # 1. Compras de Produtos (Custo na Aquisição das Mercadorias)
    if not df_produtos.empty:
        for _, r in df_produtos.iterrows():
            dt_compra = r.get("data_aquisicao") or r.get("created_at")
            custo_unit = float(pd.to_numeric(r.get("custo", 0.0), errors="coerce"))
            col_q = "qtd_comprada" if "qtd_comprada" in r else ("qtd_estoque" if "qtd_estoque" in r else "qtd")
            qtd_c = int(pd.to_numeric(r.get(col_q, 1), errors="coerce"))
            qtd_c = max(1, qtd_c)
            tot_c = custo_unit * qtd_c
            if tot_c > 0:
                lista_movimentos.append({
                    "Data_Val": dt_compra,
                    "Data": format_data_br(dt_compra),
                    "Origem": "🛍️ Aquisição de Mercadorias",
                    "Descrição": f"Compra de Estoque - {r.get('codigo','')} ({qtd_c}un)",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -tot_c
                })

    # 2. Recebimentos das Vendas
    if not df_vendas.empty:
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_vendas.columns else ("data_receb" if "data_receb" in df_vendas.columns else "data")
        for _, r in df_vendas.iterrows():
            dt_v = r.get(col_dt_rec) or r.get("data")
            val_v = float(pd.to_numeric(r.get("valor_venda") or r.get("valor") or 0.0, errors="coerce"))
            cli = r.get("cliente") or r.get("nome_cliente") or ""
            cod = r.get("codigo_bone") or r.get("codigo") or ""
            if val_v > 0:
                lista_movimentos.append({
                    "Data_Val": dt_v,
                    "Data": format_data_br(dt_v),
                    "Origem": "🛒 Recebimento de Vendas",
                    "Descrição": f"Venda {cod} - Cliente: {cli}",
                    "Tipo": "Entrada 🟢",
                    "Valor_Num": val_v
                })

    # 3. Custos de Venda e Custos das Feiras
    if not df_custos.empty:
        for _, r in df_custos.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce"))
            sub_c = str(r.get("subcategoria", "Custos"))
            desc_c = r.get("desc") or r.get("descricao") or "Despesa Avulsa"
            
            origem_tag = "🏷️ Custos de Venda" if "venda" in sub_c.lower() else ("🎪 Custos de Feiras" if "feira" in sub_c.lower() else f"💵 Custos ({sub_c})")
            
            if val_c > 0:
                lista_movimentos.append({
                    "Data_Val": r.get("data"),
                    "Data": format_data_br(r.get("data")),
                    "Origem": origem_tag,
                    "Descrição": desc_c,
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -val_c
                })

    # 4. Aporte dos Sócios
    if not df_aportes.empty:
        for _, r in df_aportes.iterrows():
            val_ap = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce"))
            tipo_ap = str(r.get("tipo", "Aporte"))
            socio = r.get("socio", "")
            is_ent = "aporte" in tipo_ap.lower() and "devolu" not in tipo_ap.lower()
            if val_ap > 0:
                lista_movimentos.append({
                    "Data_Val": r.get("data"),
                    "Data": format_data_br(r.get("data")),
                    "Origem": "🤝 Aporte dos Sócios",
                    "Descrição": f"{tipo_ap} ({socio})",
                    "Tipo": "Entrada 🟢" if is_ent else "Saída 🔴",
                    "Valor_Num": val_ap if is_ent else -val_ap
                })

    # 5. Complemento com lançamentos do Livro Caixa
    if not df_caixa.empty:
        for _, r in df_caixa.iterrows():
            desc_val = str(r.get("desc", ""))
            if not any(tag in desc_val for tag in ["Compra de Mercadorias", "Venda ", "Feira:", "[Custos de Venda]", "Aporte (", "Devolução ("]):
                d_val = r.get("data") or r.get("created_at")
                t_val = str(r.get("tipo", "Geral"))
                v_val = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce"))
                is_entrada = t_val in ["Venda", "Aporte de Sócio", "Entrada"]
                if v_val > 0:
                    lista_movimentos.append({
                        "Data_Val": d_val,
                        "Data": format_data_br(d_val),
                        "Origem": f"💰 Caixa Geral ({t_val})",
                        "Descrição": desc_val,
                        "Tipo": "Entrada 🟢" if is_entrada else "Saída 🔴",
                        "Valor_Num": v_val if is_entrada else -v_val
                    })

    if lista_movimentos:
        df_extrato = pd.DataFrame(lista_movimentos)
        
        # Conversão segura de datas para garantir ordenação homogênea sem TypeError
        df_extrato["Data_Raw"] = pd.to_datetime(df_extrato["Data_Val"], errors="coerce")
        df_extrato["Data_Raw"] = df_extrato["Data_Raw"].fillna(pd.Timestamp("1970-01-01"))
        
        # Ordenação rigorosamente cronológica
        df_extrato = df_extrato.sort_values(by="Data_Raw", ascending=True).reset_index(drop=True)
        
        # Cálculo acumulado do saldo financeiro
        df_extrato["Saldo_Acumulado"] = df_extrato["Valor_Num"].cumsum()
        
        df_extrato["Valor (R$)"] = df_extrato["Valor_Num"].apply(lambda v: f"R$ {abs(v):,.2f}")
        df_extrato["Saldo Acumulado (R$)"] = df_extrato["Saldo_Acumulado"].apply(lambda v: f"R$ {v:,.2f}")

        cols_final = ["Data", "Origem", "Descrição", "Tipo", "Valor (R$)", "Saldo Acumulado (R$)"]
        st.dataframe(df_extrato[cols_final], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada no fluxo de caixa.")

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
