import datetime
import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as _go
import streamlit as st
from supabase import Client, create_client

# 1. Configuração da Página do Streamlit
st.set_page_config(
    page_title="R² Bonés - Controle Gerencial",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS inspirada no layout HTML
st.markdown(
    """
<style>
    :root {
        --bg-color: #f4f6f8;
        --primary: #2c3e50;
        --accent: #27ae60;
        --danger: #e74c3c;
    }
    .main {
        background-color: #f4f6f8;
    }
    .kpi-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 6px;
        border-left: 5px solid #2c3e50;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .kpi-title {
        font-size: 0.85em;
        color: #666;
        margin-bottom: 5px;
        font-weight: 600;
    }
    .kpi-value {
        font-size: 1.4em;
        font-weight: bold;
        color: #2c3e50;
    }
    .header-box {
        background: #ffffff;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
</style>
""",
    unsafe_allow_kwargs=True,
)


# 2. Inicialização do Cliente Supabase
@st.cache_resource
def init_supabase() -> Client:
  try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)
  except Exception:
    st.error(
        "⚠️ Configuração do Supabase ausente! Verifique SUPABASE_URL e"
        " SUPABASE_KEY em Secrets."
    )
    st.stop()


supabase = init_supabase()


def fetch_data(table_name: str) -> pd.DataFrame:
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

# Header principal
st.markdown(
    """
<div class="header-box">
    <h2 style="margin: 0; color: #2c3e50;">🧢 R² Bonés - Controle Gerencial</h2>
</div>
""",
    unsafe_allow_kwargs=True,
)

# Flash Messages
if "flash_success" in st.session_state:
  st.success(st.session_state.pop("flash_success"))

# Cálculo de KPIs Rápidos Globais
total_faturado = (
    float(df_vendas["valor"].sum())
    if not df_vendas.empty and "valor" in df_vendas.columns
    else 0.0
)
total_cmv = (
    float(df_vendas["custo"].sum())
    if not df_vendas.empty and "custo" in df_vendas.columns
    else 0.0
)

saldo_caixa = 0.0
if (
    not df_caixa.empty
    and "valor" in df_caixa.columns
    and "tipo" in df_caixa.columns
):
  entradas = df_caixa[
      df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])
  ]["valor"].sum()
  saidas = df_caixa[
      ~df_caixa["tipo"].isin(["Venda", "Aporte de Sócio", "Entrada"])
  ]["valor"].sum()
  saldo_caixa = float(entradas - saidas)

total_estoque_qtd = (
    int(df_produtos["qtd"].sum())
    if not df_produtos.empty and "qtd" in df_produtos.columns
    else 0
)

# Cards de KPIs do Topo
k1, k2, k3, k4 = st.columns(4)
with k1:
  st.markdown(
      '<div class="kpi-card" style="border-left-color: #27ae60;"><div'
      ' class="kpi-title">Faturamento Total</div><div class="kpi-value">R$'
      f" {total_faturado:,.2f}</div></div>",
      unsafe_allow_kwargs=True,
  )
with k2:
  st.markdown(
      '<div class="kpi-card" style="border-left-color: #e74c3c;"><div'
      ' class="kpi-title">CMV (Custo Bonés Vendidos)</div><div'
      f' class="kpi-value">R$ {total_cmv:,.2f}</div></div>',
      unsafe_allow_kwargs=True,
  )
with k3:
  st.markdown(
      '<div class="kpi-card" style="border-left-color: #f39c12;"><div'
      ' class="kpi-title">Saldo em Caixa</div><div class="kpi-value">R$'
      f" {saldo_caixa:,.2f}</div></div>",
      unsafe_allow_kwargs=True,
  )
with k4:
  st.markdown(
      '<div class="kpi-card" style="border-left-color: #2980b9;"><div'
      ' class="kpi-title">Itens no Estoque</div><div'
      f' class="kpi-value">{total_estoque_qtd} un</div></div>',
      unsafe_allow_kwargs=True,
  )

st.markdown("<br>", unsafe_allow_kwargs=True)

# Navegação idêntica às Abas do HTML
menu = st.radio(
    "Navegação:",
    [
        "📈 Dashboard",
        "🛒 Vendas",
        "🛍️ Compras",
        "📦 Estoque",
        "💵 Custos",
        "🤝 Aportes dos Sócios",
        "💰 Fluxo de Caixa",
    ],
    horizontal=True,
)

st.markdown("---")

# ==============================================================================
# 1. DASHBOARD
# ==============================================================================
if menu == "📈 Dashboard":
  st.subheader("📈 Painel Executivo")

  # Filtro de mês
  meses_disponiveis = ["TODOS"]
  if not df_vendas.empty and "data" in df_vendas.columns:
    df_vendas["mes_ano"] = df_vendas["data"].astype(str).str.slice(0, 7)
    meses_disponiveis.extend(sorted(df_vendas["mes_ano"].unique().tolist()))

  mes_sel = st.selectbox("📅 Mês do Dashboard:", list(set(meses_disponiveis)))

  df_vendas_fil = df_vendas.copy()
  if mes_sel != "TODOS" and not df_vendas_fil.empty:
    df_vendas_fil = df_vendas_fil[
        df_vendas_fil["data"].astype(str).str.startswith(mes_sel)
    ]

  fat_fil = (
      float(df_vendas_fil["valor"].sum())
      if not df_vendas_fil.empty and "valor" in df_vendas_fil.columns
      else 0.0
  )
  cmv_fil = (
      float(df_vendas_fil["custo"].sum())
      if not df_vendas_fil.empty and "custo" in df_vendas_fil.columns
      else 0.0
  )
  margem = (((fat_fil - cmv_fil) / fat_fil) * 100) if fat_fil > 0 else 0.0
  ticket = (
      (fat_fil / len(df_vendas_fil))
      if not df_vendas_fil.empty and len(df_vendas_fil) > 0
      else 0.0
  )

  capital_estoque = 0.0
  if (
      not df_produtos.empty
      and "custo" in df_produtos.columns
      and "qtd" in df_produtos.columns
  ):
    capital_estoque = float((df_produtos["custo"] * df_produtos["qtd"]).sum())

  dk1, dk2, dk3 = st.columns(3)
  with dk1:
    st.markdown(
        '<div class="kpi-card" style="border-left-color: #8e44ad;"><div'
        ' class="kpi-title">Margem Bruta</div><div'
        f' class="kpi-value">{margem:.1f}%</div></div>',
        unsafe_allow_kwargs=True,
    )
  with dk2:
    st.markdown(
        '<div class="kpi-card" style="border-left-color: #16a085;"><div'
        ' class="kpi-title">Ticket Médio</div><div class="kpi-value">R$'
        f" {ticket:,.2f}</div></div>",
        unsafe_allow_kwargs=True,
    )
  with dk3:
    st.markdown(
        '<div class="kpi-card" style="border-left-color: #d35400;"><div'
        ' class="kpi-title">Capital Parado em Estoque</div><div'
        f' class="kpi-value">R$ {capital_estoque:,.2f}</div></div>',
        unsafe_allow_kwargs=True,
    )

  g1, g2 = st.columns(2)
  with g1:
    st.markdown("#### 📊 Faturamento vs. CMV (Mês a Mês)")
    if not df_vendas_fil.empty and "data" in df_vendas_fil.columns:
      df_vendas_fil["mes"] = df_vendas_fil["data"].astype(str).str.slice(0, 7)
      agrup = (
          df_vendas_fil.groupby("mes")[["valor", "custo"]].sum().reset_index()
      )
      fig1 = px.bar(
          agrup,
          x="mes",
          y=["valor", "custo"],
          barmode="group",
          labels={"value": "R$", "variable": "Tipo", "mes": "Mês"},
          color_discrete_map={"valor": "#27ae60", "custo": "#e74c3c"},
      )
      st.plotly_chart(fig1, use_container_width=True)
    else:
      st.info("Sem dados suficientes para exibir o gráfico.")

  with g2:
    st.markdown("#### 🎨 Cores Mais Vendidas (Qtd Total)")
    if (
        not df_vendas_fil.empty
        and "codigo" in df_vendas_fil.columns
        and not df_produtos.empty
    ):
      df_m = df_vendas_fil.merge(df_produtos, on="codigo", how="left")
      cor_col = "cor" if "cor" in df_m.columns else "cor_x"
      if cor_col in df_m.columns:
        agrup_cor = (
            df_m.groupby(cor_col)[
                "qtd_x" if "qtd_x" in df_m.columns else "qtd"
            ]
            .sum()
            .reset_index()
        )
        fig2 = px.pie(
            agrup_cor,
            names=cor_col,
            values="qtd_x" if "qtd_x" in agrup_cor.columns else "qtd",
            hole=0.4,
        )
        st.plotly_chart(fig2, use_container_width=True)
      else:
        st.info("Sem informações de cor nos produtos.")
    else:
      st.info("Sem vendas para exibir o gráfico de cores.")

  g3, g4 = st.columns(2)
  with g3:
    st.markdown("#### 💰 Evolução do Fluxo de Caixa")
    if not df_caixa.empty and "data" in df_caixa.columns:
      df_caixa["mes"] = df_caixa["data"].astype(str).str.slice(0, 7)
      agrup_cx = df_caixa.groupby(["mes", "tipo"])["valor"].sum().reset_index()
      fig3 = px.line(agrup_cx, x="mes", y="valor", color="tipo", markers=True)
      st.plotly_chart(fig3, use_container_width=True)
    else:
      st.info("Sem movimentações financeiras no caixa.")

  with g4:
    st.markdown("#### 🤝 Participação de Investimento dos Sócios")
    if not df_aportes.empty and "socio" in df_aportes.columns:
      agrup_soc = df_aportes.groupby("socio")["valor"].sum().reset_index()
      fig4 = px.pie(
          agrup_soc,
          names="socio",
          values="valor",
          color_discrete_map={"Renan": "#2c3e50", "Ronald": "#8e44ad"},
      )
      st.plotly_chart(fig4, use_container_width=True)
    else:
      st.info("Nenhum aporte registrado.")

# ==============================================================================
# 2. VENDAS
# ==============================================================================
elif menu == "🛒 Vendas":
  st.subheader("🛒 Lançar Nova Venda")

  if not df_produtos.empty and "codigo" in df_produtos.columns:
    opts = [
        f"[{r['codigo']}] \"{r.get('frase','')}\" (Disponível: {r.get('qtd',0)}"
        " un)"
        for _, r in df_produtos.iterrows()
    ]
    prod_sel = st.selectbox("🔍 Selecionar Produto do Estoque *", opts)

    c1, c2, c3 = st.columns(3)
    with c1:
      codigo_sel = (
          prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""
      )
      qtd_venda = st.number_input("Quantidade *", min_value=1, value=1, step=1)
      cliente = st.text_input("Nome do Cliente *")
    with c2:
      valor_venda = st.number_input(
          "Valor Total (R$) *", min_value=0.0, value=60.0, step=5.0
      )
      forma_pagto = st.selectbox(
          "Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"]
      )
    with c3:
      data_venda = st.date_input("Data da Venda *", datetime.date.today())
      data_receb = st.date_input("Data de Recebimento (Opcional)", value=None)

    if st.button("Finalizar Venda", type="primary", use_container_width=True):
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
            "custo": float(custo_unit * qtd_venda),
        }
        supabase.table("vendas").insert(nova_venda).execute()

        # Lança no Caixa apenas se houver Data de Recebimento preenchida
        if data_receb and valor_venda > 0:
          supabase.table("caixa").insert({
              "data": str(data_receb),
              "desc": (
                  f"Venda {codigo_sel} ({qtd_venda}un) - {cliente.strip()}"
              ),
              "tipo": "Venda",
              "valor": float(valor_venda),
          }).execute()

        st.session_state["flash_success"] = (
            f"🎉 Venda do boné {codigo_sel} salva com sucesso!"
        )
        st.rerun()

  st.markdown("---")
  st.subheader("📋 Histórico Detalhado de Vendas")
  if not df_vendas.empty:
    st.dataframe(df_vendas, use_container_width=True, hide_index=True)
  else:
    st.info("Nenhuma venda registrada.")

# ==============================================================================
# 3. COMPRAS
# ==============================================================================
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
      custo_c = st.number_input(
          "Custo Unitário (R$) *", min_value=0.0, value=29.0
      )
      qtd_c = st.number_input("Qtd Comprada *", min_value=1, value=1)
      dt_aquisicao = st.date_input("Data da Aquisição *", datetime.date.today())

    btn_compra = st.form_submit_button(
        "Adicionar / Atualizar Compra", use_container_width=True
    )
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
            "dataAquisicao": str(dt_aquisicao),
        }
        supabase.table("produtos").upsert(
            novo_prod, on_conflict="codigo"
        ).execute()

        # Lançamento automático no caixa para compra de estoque
        custo_total = float(custo_c * qtd_c)
        if custo_total > 0:
          supabase.table("caixa").insert({
              "data": str(dt_aquisicao),
              "desc": "Compra de Mercadorias (Estoque)",
              "tipo": "Compra de Mercadorias",
              "valor": custo_total,
          }).execute()

        st.session_state["flash_success"] = (
            f"🎉 Compra do produto {cod_c} registrada com sucesso!"
        )
        st.rerun()

  st.markdown("---")
  st.subheader("📋 Histórico Permanente de Aquisições")
  if not df_produtos.empty:
    st.dataframe(df_produtos, use_container_width=True, hide_index=True)
  else:
    st.info("Nenhuma aquisição registrada.")

# ==============================================================================
# 4. ESTOQUE
# ==============================================================================
elif menu == "📦 Estoque":
  st.subheader("📦 Estoque Atual em Tempo Real (Saldo Disponível)")
  st.caption("Esta aba reflete os saldos disponíveis em estoque.")

  if not df_produtos.empty:
    df_est = df_produtos.copy()
    df_est["Status"] = "Disponível"
    st.dataframe(df_est, use_container_width=True, hide_index=True)
  else:
    st.info("Estoque vazio no momento.")

# ==============================================================================
# 5. CUSTOS
# ==============================================================================
elif menu == "💵 Custos":
  st.subheader("💵 Gerenciamento de Custos e Despesas")

  sub_tab = st.radio(
      "Sub-abas de Custos:",
      ["📦 Mercadorias", "🏷️ Custos de Venda", "🎪 Feiras"],
      horizontal=True,
  )

  if sub_tab == "📦 Mercadorias":
    st.markdown("#### Histórico Agrupado de Aquisições de Mercadorias")
    if not df_produtos.empty:
      df_m = df_produtos.copy()
      df_m["Custo Total"] = df_m["custo"] * df_m["qtd"]
      st.dataframe(
          df_m[["dataAquisicao", "categoria", "qtd", "custo", "Custo Total"]],
          use_container_width=True,
          hide_index=True,
      )
    else:
      st.info("Nenhuma mercadoria cadastrada.")

  elif sub_tab == "🏷️️ Custos de Venda":
    st.markdown("#### Lançar / Registrar Custo de Venda")
    with st.form("form_cv"):
      c1, c2, c3 = st.columns(3)
      with c1:
        dt_cv = st.date_input("Data *", datetime.date.today())
        desc_cv = st.text_input("Descrição *")
      with c2:
        tipo_cv = st.selectbox(
            "Tipo de Despesa *", ["Brindes", "Embalagem", "Unboxing"]
        )
      with c3:
        val_cv = st.number_input("Valor (R$) *", min_value=0.01, value=10.0)

      if st.form_submit_button(
          "Adicionar Custo de Venda", use_container_width=True
      ):
        c_dict = {
            "subcategoria": "Custos de Venda",
            "data": str(dt_cv),
            "desc": desc_cv.strip(),
            "tipo": tipo_cv,
            "valor": float(val_cv),
        }
        supabase.table("custos_avulsos").insert(c_dict).execute()
        supabase.table("caixa").insert({
            "data": str(dt_cv),
            "desc": f"[Custos de Venda] {desc_cv.strip()}",
            "tipo": tipo_cv,
            "valor": float(val_cv),
        }).execute()
        st.session_state["flash_success"] = (
            "Custo de venda registrado com sucesso!"
        )
        st.rerun()

  elif sub_tab == "🎪 Feiras":
    st.markdown("#### Lançar / Registrar Custo de Feiras")
    with st.form("form_cf"):
      c1, c2, c3 = st.columns(3)
      with c1:
        dt_cf = st.date_input("Data *", datetime.date.today())
        feira_cf = st.text_input("Nome da Feira (ex: Feirarte) *")
      with c2:
        desc_cf = st.text_input("Descrição da despesa *")
        tipo_cf = st.selectbox(
            "Tipo de Despesa *",
            [
                "Alimentação",
                "Decoração",
                "Instalação",
                "Taxa de Inscrição",
                "Transporte",
            ],
        )
      with c3:
        val_cf = st.number_input("Valor (R$) *", min_value=0.01, value=50.0)

      if st.form_submit_button(
          "Adicionar Custo de Feira", use_container_width=True
      ):
        c_dict = {
            "subcategoria": "Feiras",
            "data": str(dt_cf),
            "nomeFeira": feira_cf.strip(),
            "desc": desc_cf.strip(),
            "tipo": tipo_cf,
            "valor": float(val_cf),
        }
        supabase.table("custos_avulsos").insert(c_dict).execute()
        supabase.table("caixa").insert({
            "data": str(dt_cf),
            "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}",
            "tipo": tipo_cf,
            "valor": float(val_cf),
        }).execute()
        st.session_state["flash_success"] = (
            "Custo de feira registrado com sucesso!"
        )
        st.rerun()

# ==============================================================================
# 6. APORTES DOS SÓCIOS
# ==============================================================================
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
    if st.button(
        "🤝 Registrar Aporte", use_container_width=True, type="primary"
    ):
      supabase.table("aportes").insert({
          "data": str(dt_ap),
          "socio": socio_ap,
          "valor": float(val_ap),
          "tipo": "Aporte",
      }).execute()
      supabase.table("caixa").insert({
          "data": str(dt_ap),
          "desc": f"Aporte ({socio_ap})",
          "tipo": "Aporte de Sócio",
          "valor": float(val_ap),
      }).execute()
      st.session_state["flash_success"] = (
          f"Aporte de R$ {val_ap:.2f} registrado para {socio_ap}!"
      )
      st.rerun()

  with col_btn2:
    if st.button("🔄 Devolução de Aporte", use_container_width=True):
      supabase.table("aportes").insert({
          "data": str(dt_ap),
          "socio": socio_ap,
          "valor": float(val_ap),
          "tipo": "Devolução",
      }).execute()
      supabase.table("caixa").insert({
          "data": str(dt_ap),
          "desc": f"Devolução ({socio_ap})",
          "tipo": "Devolução de Aporte",
          "valor": float(val_ap),
      }).execute()
      st.session_state["flash_success"] = (
          f"Devolução de R$ {val_ap:.2f} registrada para {socio_ap}!"
      )
      st.rerun()

  st.markdown("---")
  st.subheader("Resumo dos Sócios")
  if not df_aportes.empty:
    totais = df_aportes.groupby("socio")["valor"].sum().reset_index()
    st.dataframe(totais, use_container_width=True, hide_index=True)

# ==============================================================================
# 7. FLUXO DE CAIXA
# ==============================================================================
elif menu == "💰 Fluxo de Caixa":
  st.subheader("💰 Extrato Consolidado de Caixa (Repositório)")
  st.caption(
      "Exibe o extrato consolidado com o saldo acumulado após cada"
      " movimentação."
  )

  if not df_caixa.empty:
    st.dataframe(df_caixa, use_container_width=True, hide_index=True)
  else:
    st.info("Nenhuma movimentação no caixa.")
