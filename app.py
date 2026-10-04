import datetime
import io
import time
import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import Client, create_client

# 1. Configuração da Página do Streamlit
st.set_page_config(
    page_title="R2 Bonés - Gestão de Vendas & Estoque",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 2. Inicialização do Cliente Supabase
@st.cache_resource
def init_supabase() -> Client:
  try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)
  except Exception as e:
    st.error(
        "⚠️ Configuração do Supabase ausente! Adicione SUPABASE_URL e"
        " SUPABASE_KEY em st.secrets."
    )
    st.stop()


supabase = init_supabase()


# Helper para executar operações no Supabase com suporte a reconexão automática
def execute_supabase_operation(operation_func, max_retries=2, delay=1):
  last_err = None
  for attempt in range(max_retries):
    try:
      return operation_func()
    except Exception as e:
      last_err = e
      if attempt < max_retries - 1:
        time.sleep(delay)
  raise last_err


# 3. Função Helper para buscar tabelas em tempo real com retry
def fetch_data(table_name: str) -> pd.DataFrame:
  try:

    def query():
      res = supabase.table(table_name).select("*").execute()
      return pd.DataFrame(res.data)

    return execute_supabase_operation(query)
  except Exception:
    return pd.DataFrame()


# Layout Principal
st.title("🧢 R2 Bonés Personalizados")
st.caption("Sistema de Gestão Integrada para Sócios (Renan & Ronald)")

# Menu Lateral (Sidebar)
st.sidebar.title("Menu R2 Bonés")
menu = st.sidebar.radio(
    "Navegação:",
    [
        "📊 Dashboard KPIs",
        "🛒 Nova Venda",
        "📦 Catálogo & Estoque",
        "💰 Fluxo de Caixa",
        "🤝 Aportes dos Sócios",
        "📂 Importar/Exportar Excel",
        "💾 Gestão de Dados",
    ],
)

# Carrega Dados do Supabase
df_produtos = fetch_data("produtos")
df_vendas = fetch_data("vendas")
df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")

# Mensagem temporária de sucesso mantida em session_state
if "flash_success" in st.session_state:
  st.success(st.session_state.pop("flash_success"))

# ==============================================================================
# ABA 1: DASHBOARD DE KPIS
# ==============================================================================
if menu == "📊 Dashboard KPIs":
  st.subheader("📊 Indicadores Gerais de Desempenho")

  total_faturado = (
      float(df_vendas["valor_venda"].sum()) if not df_vendas.empty else 0.0
  )
  total_cmv = (
      float(df_vendas["custo_unitario"].sum()) if not df_vendas.empty else 0.0
  )
  lucro_bruto = total_faturado - total_cmv

  entradas_caixa = (
      float(df_caixa[df_caixa["tipo"] == "Entrada"]["valor"].sum())
      if not df_caixa.empty
      else 0.0
  )
  saidas_caixa = (
      float(df_caixa[df_caixa["tipo"] == "Saída"]["valor"].sum())
      if not df_caixa.empty
      else 0.0
  )
  saldo_caixa = entradas_caixa - saidas_caixa

  qtd_estoque = (
      int(df_produtos["qtd_estoque"].sum()) if not df_produtos.empty else 0
  )

  col1, col2, col3, col4, col5 = st.columns(5)
  col1.metric("Faturamento Total", f"R$ {total_faturado:,.2f}")
  col2.metric("CMV (Custo Bonés)", f"R$ {total_cmv:,.2f}")
  col3.metric("Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
  col4.metric("Saldo em Caixa", f"R$ {saldo_caixa:,.2f}")
  col5.metric("Estoque Disponível", f"{qtd_estoque} un")

  st.markdown("---")

  if not df_vendas.empty:
    c1, c2 = st.columns(2)
    with c1:
      st.markdown("##### 📈 Faturamento por Forma de Pagamento")
      fig_pagto = px.pie(
          df_vendas,
          names="forma_pagto",
          values="valor_venda",
          hole=0.4,
          color_discrete_sequence=px.colors.qualitative.Set2,
      )
      st.plotly_chart(fig_pagto, use_container_width=True)
    with c2:
      st.markdown("##### 🏆 Bonés Mais Vendidos (R$)")
      top_bones = (
          df_vendas.groupby("codigo_bone")["valor_venda"].sum().reset_index()
      )
      fig_top = px.bar(
          top_bones,
          x="codigo_bone",
          y="valor_venda",
          labels={"codigo_bone": "Código", "valor_venda": "Total (R$)"},
          color_discrete_sequence=["#1F4E78"],
      )
      st.plotly_chart(fig_top, use_container_width=True)
  else:
    st.info("Nenhuma venda registrada até o momento.")

# ==============================================================================
# ABA 2: NOVA VENDA
# ==============================================================================
elif menu == "🛒 Nova Venda":
  st.subheader("🛒 Lançamento de Nova Venda")

  if df_produtos.empty:
    st.warning(
        "Nenhum produto cadastrado no catálogo. Adicione bonés no catálogo"
        " primeiro."
    )
  else:
    disponiveis = df_produtos[df_produtos["qtd_estoque"] > 0]

    if disponiveis.empty:
      st.error("⚠️ Não há bonés disponíveis em estoque no momento!")
    else:
      if "venda_cliente" not in st.session_state:
        st.session_state["venda_cliente"] = ""

      col_a, col_b = st.columns(2)
      with col_a:
        opcao_bone = st.selectbox(
            "Selecione o Boné em Estoque *",
            disponiveis["codigo"].tolist(),
            key="venda_bone",
        )
        cliente = st.text_input("Nome do Cliente *", key="venda_cliente")

        val_sugerido = 60.0
        if opcao_bone:
          cat_row = df_produtos[df_produtos["codigo"] == opcao_bone]
          if not cat_row.empty and cat_row["categoria"].values[0] == "Premium":
            val_sugerido = 65.0

        valor_venda = st.number_input(
            "Valor de Venda (R$) *",
            value=val_sugerido,
            min_value=0.0,
            step=5.0,
            key="venda_valor",
        )
      with col_b:
        forma_pagto = st.selectbox(
            "Forma de Pagamento *",
            ["PIX", "Cartão", "Dinheiro", "Brinde"],
            key="venda_pagto",
        )
        data_venda = st.date_input(
            "Data da Venda", datetime.date.today(), key="venda_data"
        )

      btn_venda = st.button("✅ Finalizar Venda", use_container_width=True)
      if btn_venda:
        if not cliente.strip():
          st.error("Por favor, informe o nome do cliente!")
        else:
          venda_sucesso = False
          try:
            prod_info = df_produtos[
                df_produtos["codigo"] == opcao_bone
            ].iloc[0]

            def op_venda():
              nova_venda = {
                  "codigo_bone": opcao_bone,
                  "produto_id": int(prod_info["id"]),
                  "cliente": cliente.strip(),
                  "valor_venda": valor_venda,
                  "custo_unitario": float(prod_info["custo"]),
                  "forma_pagto": forma_pagto,
                  "data_venda": str(data_venda),
              }
              supabase.table("vendas").insert(nova_venda).execute()

              nova_qtd = int(prod_info["qtd_estoque"]) - 1
              supabase.table("produtos").update({"qtd_estoque": nova_qtd}).eq(
                  "id", prod_info["id"]
              ).execute()

              if valor_venda > 0:
                novo_caixa = {
                    "data_movimentacao": str(data_venda),
                    "descricao": f"Venda {opcao_bone} - {cliente.strip()}",
                    "tipo": "Entrada",
                    "valor": valor_venda,
                }
                supabase.table("caixa").insert(novo_caixa).execute()

            execute_supabase_operation(op_venda)
            venda_sucesso = True
          except Exception:
            st.error(
                "🌐 Erro de Conexão com o Supabase. Verifique sua conexão e"
                " tente novamente."
            )

          if venda_sucesso:
            st.session_state["flash_success"] = (
                f"🎉 Venda do boné {opcao_bone} para {cliente} salva"
                " permanentemente!"
            )
            st.session_state["venda_cliente"] = ""
            st.rerun()

  st.markdown("---")
  st.subheader("📋 Histórico de Vendas")
  st.dataframe(df_vendas, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA 3: CATÁLOGO & ESTOQUE
# ==============================================================================
elif menu == "📦 Catálogo & Estoque":
  st.subheader("📦 Cadastrar Novo Boné")

  c1, c2, c3 = st.columns(3)
  with c1:
    codigo = st.text_input("Código do Boné (ex: BL-0001) *", key="prod_codigo")
    cor = st.text_input("Cor do Boné *", key="prod_cor")
  with c2:
    frase = st.text_input("Frase Estampada *", key="prod_frase")
    categoria = st.selectbox(
        "Categoria", ["Básico", "Premium", "Liso"], key="prod_cat"
    )
  with c3:
    custo = st.number_input(
        "Custo Unitário (R$)", value=29.0, step=1.0, key="prod_custo"
    )
    qtd = st.number_input(
        "Qtd em Estoque", value=1, min_value=0, step=1, key="prod_qtd"
    )

  btn_prod = st.button("➕ Salvar no Catálogo", use_container_width=True)
  if btn_prod:
    if not codigo.strip() or not cor.strip() or not frase.strip():
      st.error("Preencha Código, Cor e Frase obrigatoriamente!")
    else:
      salvou_com_sucesso = False
      try:
        novo_prod = {
            "codigo": codigo.strip(),
            "cor": cor.strip(),
            "frase": frase.strip(),
            "categoria": categoria,
            "custo": custo,
            "qtd_estoque": qtd,
        }
        execute_supabase_operation(
            lambda: supabase.table("produtos")
            .upsert(novo_prod, on_conflict="codigo")
            .execute()
        )
        salvou_com_sucesso = True
      except Exception:
        st.error(
            "🌐 Erro de Conexão com o Banco de Dados. Verifique sua conexão e"
            " tente novamente."
        )

      if salvou_com_sucesso:
        st.session_state["flash_success"] = (
            f"🎉 Boné {codigo.strip()} gravado com sucesso no Supabase!"
        )
        st.session_state["prod_codigo"] = ""
        st.session_state["prod_cor"] = ""
        st.session_state["prod_frase"] = ""
        st.rerun()

  st.markdown("---")
  st.subheader("📦 Produtos em Estoque")

  if not df_produtos.empty:
    df_display = df_produtos.copy()

    for col in ["cor_estampa", "categoria", "custo"]:
      if col not in df_display.columns:
        df_display[col] = (
            "None"
            if col == "cor_estampa"
            else ("Básico" if col == "categoria" else 29.0)
        )

    renames = {
        "codigo": "Código",
        "cor": "Cor do Boné",
        "frase": "Arte Estampada",
        "cor_estampa": "Cor da Estampa",
        "categoria": "Produto",
        "custo": "Custo",
    }

    cols_presentes = [c for c in renames.keys() if c in df_display.columns]
    df_filtered = df_display[cols_presentes].rename(columns=renames)

    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

    # ======================================================================
    # OPÇÃO PARA ALTERAR OU EXCLUIR PRODUTOS JÁ INSERIDOS
    # ======================================================================
    st.markdown("---")
    st.subheader("✏️ Alterar ou Excluir Produto Cadastrado")

    lista_codigos = df_produtos["codigo"].unique().tolist()
    cod_selecionado = st.selectbox(
        "Selecione o Código do Boné para Gerenciar:", lista_codigos
    )

    if cod_selecionado:
      prod_row = df_produtos[df_produtos["codigo"] == cod_selecionado].iloc[0]

      with st.expander(
          f"⚙️ Opções para o Boné: **{cod_selecionado}**", expanded=True
      ):
        ec1, ec2 = st.columns(2)
        with ec1:
          edit_cor = st.text_input(
              "Cor do Boné",
              value=str(prod_row.get("cor", "")),
              key="edit_cor",
          )
          edit_frase = st.text_input(
              "Arte Estampada",
              value=str(prod_row.get("frase", "")),
              key="edit_frase",
          )
          edit_cor_estampa = st.text_input(
              "Cor da Estampa",
              value=str(prod_row.get("cor_estampa", "None")),
              key="edit_cor_estampa",
          )
        with ec2:
          cat_atual = str(prod_row.get("categoria", "Básico"))
          opts_cat = ["Básico", "Premium", "Liso"]
          idx_cat = (
              opts_cat.index(cat_atual) if cat_atual in opts_cat else 0
          )
          edit_cat = st.selectbox(
              "Produto (Categoria)",
              opts_cat,
              index=idx_cat,
              key="edit_cat",
          )
          edit_custo = st.number_input(
              "Custo (R$)",
              value=float(prod_row.get("custo", 29.0)),
              step=1.0,
              key="edit_custo",
          )

        col_bt1, col_bt2 = st.columns(2)
        with col_bt1:
          if st.button(
              "💾 Salvar Alterações", use_container_width=True, type="primary"
          ):
            try:
              prod_upd = {
                  "codigo": cod_selecionado,
                  "cor": edit_cor.strip(),
                  "frase": edit_frase.strip(),
                  "cor_estampa": edit_cor_estampa.strip(),
                  "categoria": edit_cat,
                  "custo": edit_custo,
              }
              execute_supabase_operation(
                  lambda: supabase.table("produtos")
                  .update(prod_upd)
                  .eq("codigo", cod_selecionado)
                  .execute()
              )
              st.session_state["flash_success"] = (
                  f"✅ Produto {cod_selecionado} atualizado com sucesso!"
              )
              st.rerun()
            except Exception as e:
              st.error(f"Erro ao atualizar produto: {e}")

        with col_bt2:
          if st.button("🗑️ Excluir Produto", use_container_width=True):
            try:
              execute_supabase_operation(
                  lambda: supabase.table("produtos")
                  .delete()
                  .eq("codigo", cod_selecionado)
                  .execute()
              )
              st.session_state["flash_success"] = (
                  f"🗑️ Produto {cod_selecionado} excluído com sucesso!"
              )
              st.rerun()
            except Exception as e:
              st.error(f"Erro ao excluir produto: {e}")
  else:
    st.info("Nenhum produto em estoque.")

# ==============================================================================
# ABA 4: FLUXO DE CAIXA
# ==============================================================================
elif menu == "💰 Fluxo de Caixa":
  st.subheader("💰 Lançar Movimentação de Caixa")

  c1, c2 = st.columns(2)
  with c1:
    desc = st.text_input(
        "Descrição (Ex: Sacolas, Frete, Compra Tecido) *", key="cx_desc"
    )
    tipo = st.selectbox("Tipo *", ["Saída", "Entrada"], key="cx_tipo")
  with c2:
    valor = st.number_input(
        "Valor (R$) *", min_value=0.01, step=10.0, key="cx_valor"
    )
    data_mov = st.date_input(
        "Data da Movimentação", datetime.date.today(), key="cx_data"
    )

  btn_cx = st.button("💵 Lançar no Caixa", use_container_width=True)
  if btn_cx:
    if not desc.strip():
      st.error("Informe a descrição da movimentação!")
    else:
      cx_sucesso = False
      try:
        lancamento = {
            "data_movimentacao": str(data_mov),
            "descricao": desc.strip(),
            "tipo": tipo,
            "valor": valor,
        }
        execute_supabase_operation(
            lambda: supabase.table("caixa").insert(lancamento).execute()
        )
        cx_sucesso = True
      except Exception:
        st.error(
            "🌐 Sem Conexão com a Internet. Verifique sua rede e tente"
            " novamente."
        )

      if cx_sucesso:
        st.session_state["flash_success"] = (
            "💰 Movimentação financeira gravada permanentemente!"
        )
        st.session_state["cx_desc"] = ""
        st.rerun()

  st.markdown("---")
  st.subheader("📜 Extrato de Caixa")
  st.dataframe(df_caixa, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA 5: APORTES DOS SÓCIOS
# ==============================================================================
elif menu == "🤝 Aportes dos Sócios":
  st.subheader("🤝 Registro de Aporte de Capital")

  c1, c2 = st.columns(2)
  with c1:
    socio = st.selectbox(
        "Sócio Investidor *", ["Renan", "Ronald"], key="ap_socio"
    )
    valor_ap = st.number_input(
        "Valor do Aporte (R$) *", min_value=1.0, step=50.0, key="ap_valor"
    )
  with c2:
    data_ap = st.date_input(
        "Data do Aporte", datetime.date.today(), key="ap_data"
    )

  btn_ap = st.button("📥 Confirmar Aporte", use_container_width=True)
  if btn_ap:
    ap_sucesso = False
    try:

      def op_aporte():
        novo_aporte = {
            "data_aporte": str(data_ap),
            "socio": socio,
            "valor": valor_ap,
        }
        supabase.table("aportes").insert(novo_aporte).execute()

        supabase.table("caixa").insert({
            "data_movimentacao": str(data_ap),
            "descricao": f"Aporte Sócio ({socio})",
            "tipo": "Entrada",
            "valor": valor_ap,
        }).execute()

      execute_supabase_operation(op_aporte)
      ap_sucesso = True
    except Exception:
      st.error(
          "🌐 Sem Conexão com a Internet. Verifique sua rede e tente"
          " novamente."
      )

    if ap_sucesso:
      st.session_state["flash_success"] = (
          f"🤝 Aporte de R$ {valor_ap:.2f} do sócio {socio} registrado no banco!"
      )
      st.rerun()

  st.markdown("---")
  st.subheader("📊 Totais Investidos por Sócio")
  if not df_aportes.empty:
    totais = df_aportes.groupby("socio")["valor"].sum().reset_index()
    st.dataframe(totais, use_container_width=True, hide_index=True)
  else:
    st.info("Nenhum aporte registrado ainda.")

# ==============================================================================
# ABA 6: IMPORTAR EXCEL
# ==============================================================================
elif menu == "📂 Importar/Exportar Excel":
  st.subheader("📊 Sincronizar Planilha Excel (.xlsx)")
  st.info(
      "Esta ferramenta importa dados das abas **Matriz**, **Estoque** e"
      " **Caixa** diretamente para o banco de dados Supabase."
  )

  uploaded_file = st.file_uploader(
      "Selecione o arquivo Excel do R2 Bonés (ex: Bonés.xlsx)",
      type=["xlsx", "xls"],
  )

  if uploaded_file:
    try:
      xls = pd.ExcelFile(uploaded_file)
      sheets = xls.sheet_names
      st.write(f"📋 **Abas identificadas no arquivo:** `{', '.join(sheets)}`")

      tab_matriz, tab_estoque, tab_caixa = st.tabs(
          ["📋 Aba Matriz", "📦 Aba Estoque", "💰 Aba Caixa"]
      )

      with tab_matriz:
        if "Matriz" in sheets:
          df_matriz = pd.read_excel(uploaded_file, sheet_name="Matriz")
          st.dataframe(
              df_matriz.head(5), use_container_width=True, hide_index=True
          )

          if st.button(
              "🚀 Importar Dados da Matriz",
              key="btn_imp_matriz",
              use_container_width=True,
          ):
            try:
              prod_count, venda_count = 0, 0
              for _, row in df_matriz.iterrows():
                cod = str(row.get("CÓDIGO", "")).strip()
                if cod and cod != "nan":
                  cor = (
                      str(row.get("COR", "")).strip()
                      if pd.notna(row.get("COR"))
                      else ""
                  )
                  frase = (
                      str(row.get("FRASE ESTAMPADA", "")).strip()
                      if pd.notna(row.get("FRASE ESTAMPADA"))
                      else ""
                  )
                  cor_estampa = (
                      str(row.get("FRASE ESTAMPADA-COR", "")).strip()
                      if pd.notna(row.get("FRASE ESTAMPADA-COR"))
                      else ""
                  )
                  categoria = (
                      str(row.get("CATEGORIA", "Básico")).strip()
                      if pd.notna(row.get("CATEGORIA"))
                      else "Básico"
                  )
                  custo = (
                      float(row.get("Unnamed: 6", 29.0))
                      if pd.notna(row.get("Unnamed: 6"))
                      else 29.0
                  )
                  qtd_estoque = (
                      int(row.get("Estoque", 1))
                      if pd.notna(row.get("Estoque"))
                      else 1
                  )

                  prod_dict = {
                      "codigo": cod,
                      "cor": cor,
                      "frase": frase,
                      "cor_estampa": cor_estampa,
                      "categoria": categoria,
                      "custo": custo,
                      "qtd_estoque": qtd_estoque,
                  }
                  execute_supabase_operation(
                      lambda: supabase.table("produtos")
                      .upsert(prod_dict, on_conflict="codigo")
                      .execute()
                  )
                  prod_count += 1

                  cliente = (
                      str(row.get("Cliente", "")).strip()
                      if pd.notna(row.get("Cliente"))
                      else ""
                  )
                  valor_venda = (
                      float(row.get("Unnamed: 9", 0))
                      if pd.notna(row.get("Unnamed: 9"))
                      else 0.0
                  )
                  data_venda = (
                      row.get("Venda")
                      if pd.notna(row.get("Venda"))
                      else row.get("Recebimento")
                  )

                  if (cliente and cliente != "nan") or valor_venda > 0:
                    data_str = (
                        str(data_venda)[:10]
                        if pd.notna(data_venda)
                        else str(datetime.date.today())
                    )
                    pagto = (
                        str(row.get("Forma de Receb", "PIX")).strip()
                        if pd.notna(row.get("Forma de Receb"))
                        else "PIX"
                    )

                    venda_dict = {
                        "codigo_bone": cod,
                        "cliente": (
                            cliente if cliente != "nan" else "Cliente Geral"
                        ),
                        "valor_venda": valor_venda,
                        "custo_unitario": custo,
                        "forma_pagto": pagto,
                        "data_venda": data_str,
                    }
                    execute_supabase_operation(
                        lambda: supabase.table("vendas")
                        .insert(venda_dict)
                        .execute()
                    )
                    venda_count += 1

              st.session_state["flash_success"] = (
                  f"🎉 Matriz Importada: {prod_count} produtos e {venda_count}"
                  " vendas inseridas!"
              )
              st.rerun()
            except Exception:
              st.error("🌐 Erro de Conexão com a Internet ao importar a Matriz.")

      with tab_estoque:
        if "Estoque" in sheets:
          df_estoque = pd.read_excel(uploaded_file, sheet_name="Estoque")
          st.dataframe(
              df_estoque.head(5), use_container_width=True, hide_index=True
          )

          if st.button(
              "🚀 Importar/Atualizar Estoque",
              key="btn_imp_estoque",
              use_container_width=True,
          ):
            try:
              est_count = 0
              for _, row in df_estoque.iterrows():
                cod = str(row.get("CÓDIGO", "")).strip()
                if cod and cod != "nan":
                  cor = (
                      str(row.get("Cor", "")).strip()
                      if pd.notna(row.get("Cor"))
                      else ""
                  )
                  frase = (
                      str(row.get("Frase", "")).strip()
                      if pd.notna(row.get("Frase"))
                      else ""
                  )
                  categoria = (
                      str(row.get("Categoria", "Básico")).strip()
                      if pd.notna(row.get("Categoria"))
                      else "Básico"
                  )
                  qtd = (
                      int(row.get("Quantidade", 1))
                      if (
                          pd.notna(row.get("Quantidade"))
                          and str(row.get("Quantidade")) != "nan"
                      )
                      else 1
                  )

                  est_dict = {
                      "codigo": cod,
                      "cor": cor,
                      "frase": frase,
                      "categoria": categoria,
                      "qtd_estoque": qtd,
                  }
                  execute_supabase_operation(
                      lambda: supabase.table("produtos")
                      .upsert(est_dict, on_conflict="codigo")
                      .execute()
                  )
                  est_count += 1

              st.session_state["flash_success"] = (
                  f"🎉 Estoque Sincronizado: {est_count} bonés atualizados!"
              )
              st.rerun()
            except Exception:
              st.error(
                  "🌐 Erro de Conexão com a Internet ao importar Estoque."
              )

      with tab_caixa:
        if "Caixa" in sheets:
          df_caixa = pd.read_excel(uploaded_file, sheet_name="Caixa")
          st.dataframe(
              df_caixa.head(5), use_container_width=True, hide_index=True
          )

          if st.button(
              "🚀 Importar Caixa & Aportes",
              key="btn_imp_caixa",
              use_container_width=True,
          ):
            try:
              cx_count, ap_count = 0, 0
              for _, row in df_caixa.iterrows():
                desc = (
                    str(row.get("DESCRIÇÃO", "")).strip()
                    if pd.notna(row.get("DESCRIÇÃO"))
                    else ""
                )
                if desc and desc != "nan":
                  tipo = (
                      str(row.get("TIPO", "Entrada")).strip()
                      if pd.notna(row.get("TIPO"))
                      else "Entrada"
                  )
                  if tipo not in ["Entrada", "Saída"]:
                    tipo = "Entrada"

                  dt = row.get("DATA")
                  data_str = (
                      str(dt)[:10]
                      if pd.notna(dt)
                      else str(datetime.date.today())
                  )
                  valor = (
                      float(
                          row.get("ENTRADA R$", 0)
                          if tipo == "Entrada"
                          else row.get("SAÍDA R$", 0)
                      )
                      if pd.notna(
                          row.get("ENTRADA R$")
                          if tipo == "Entrada"
                          else row.get("SAÍDA R$")
                      )
                      else 0.0
                  )

                  caixa_dict = {
                      "data_movimentacao": data_str,
                      "descricao": desc,
                      "tipo": tipo,
                      "valor": valor,
                  }
                  execute_supabase_operation(
                      lambda: supabase.table("caixa")
                      .insert(caixa_dict)
                      .execute()
                  )
                  cx_count += 1

                  cat = (
                      str(row.get("CATEGORIA", "")).strip()
                      if pd.notna(row.get("CATEGORIA"))
                      else ""
                  )
                  if cat == "Aporte" or "Empréstimo" in desc or "Aporte" in desc:
                    socio = (
                        "Renan"
                        if "Renan" in desc
                        else ("Ronald" if "Ronald" in desc else "Renan")
                    )
                    aporte_dict = {
                        "data_aporte": data_str,
                        "socio": socio,
                        "valor": valor,
                    }
                    execute_supabase_operation(
                        lambda: supabase.table("aportes")
                        .insert(aporte_dict)
                        .execute()
                    )
                    ap_count += 1

              st.session_state["flash_success"] = (
                  f"🎉 Caixa Importado: {cx_count} lançamentos e {ap_count}"
                  " aportes inseridos!"
              )
              st.rerun()
            except Exception:
              st.error("🌐 Erro de Conexão com a Internet ao importar Caixa.")

      st.markdown("---")
      if st.button(
          "🌟 Importar TUDO de uma Só Vez (Matriz + Estoque + Caixa)",
          use_container_width=True,
          type="primary",
      ):
        try:
          total_prods, total_vendas, total_caixa, total_aportes = 0, 0, 0, 0

          if "Matriz" in sheets:
            df_m = pd.read_excel(uploaded_file, sheet_name="Matriz")
            for _, row in df_m.iterrows():
              cod = str(row.get("CÓDIGO", "")).strip()
              if cod and cod != "nan":
                cor = (
                    str(row.get("COR", "")).strip()
                    if pd.notna(row.get("COR"))
                    else ""
                )
                frase = (
                    str(row.get("FRASE ESTAMPADA", "")).strip()
                    if pd.notna(row.get("FRASE ESTAMPADA"))
                    else ""
                )
                cor_estampa = (
                    str(row.get("FRASE ESTAMPADA-COR", "")).strip()
                    if pd.notna(row.get("FRASE ESTAMPADA-COR"))
                    else ""
                )
                categoria = (
                    str(row.get("CATEGORIA", "Básico")).strip()
                    if pd.notna(row.get("CATEGORIA"))
                    else "Básico"
                )
                custo = (
                    float(row.get("Unnamed: 6", 29.0))
                    if pd.notna(row.get("Unnamed: 6"))
                    else 29.0
                )
                qtd_estoque = (
                    int(row.get("Estoque", 1))
                    if pd.notna(row.get("Estoque"))
                    else 1
                )

                prod_dict = {
                    "codigo": cod,
                    "cor": cor,
                    "frase": frase,
                    "cor_estampa": cor_estampa,
                    "categoria": categoria,
                    "custo": custo,
                    "qtd_estoque": qtd_estoque,
                }
                execute_supabase_operation(
                    lambda: supabase.table("produtos")
                    .upsert(prod_dict, on_conflict="codigo")
                    .execute()
                )
                total_prods += 1

                cliente = (
                    str(row.get("Cliente", "")).strip()
                    if pd.notna(row.get("Cliente"))
                    else ""
                )
                valor_venda = (
                    float(row.get("Unnamed: 9", 0))
                    if pd.notna(row.get("Unnamed: 9"))
                    else 0.0
                )
                data_venda = (
                    row.get("Venda")
                    if pd.notna(row.get("Venda"))
                    else row.get("Recebimento")
                )

                if (cliente and cliente != "nan") or valor_venda > 0:
                  data_str = (
                      str(data_venda)[:10]
                      if pd.notna(data_venda)
                      else str(datetime.date.today())
                  )
                  pagto = (
                      str(row.get("Forma de Receb", "PIX")).strip()
                      if pd.notna(row.get("Forma de Receb"))
                      else "PIX"
                  )
                  venda_dict = {
                      "codigo_bone": cod,
                      "cliente": cliente if cliente != "nan" else "Cliente Geral",
                      "valor_venda": valor_venda,
                      "custo_unitario": custo,
                      "forma_pagto": pagto,
                      "data_venda": data_str,
                  }
                  execute_supabase_operation(
                      lambda: supabase.table("vendas")
                      .insert(venda_dict)
                      .execute()
                  )
                  total_vendas += 1

          if "Estoque" in sheets:
            df_e = pd.read_excel(uploaded_file, sheet_name="Estoque")
            for _, row in df_e.iterrows():
              cod = str(row.get("CÓDIGO", "")).strip()
              if cod and cod != "nan":
                cor = (
                    str(row.get("Cor", "")).strip()
                    if pd.notna(row.get("Cor"))
                    else ""
                )
                frase = (
                    str(row.get("Frase", "")).strip()
                    if pd.notna(row.get("Frase"))
                    else ""
                )
                categoria = (
                    str(row.get("Categoria", "Básico")).strip()
                    if pd.notna(row.get("Categoria"))
                    else "Básico"
                )
                qtd = (
                    int(row.get("Quantidade", 1))
                    if (
                        pd.notna(row.get("Quantidade"))
                        and str(row.get("Quantidade")) != "nan"
                    )
                    else 1
                )
                est_dict = {
                    "codigo": cod,
                    "cor": cor,
                    "frase": frase,
                    "categoria": categoria,
                    "qtd_estoque": qtd,
                }
                execute_supabase_operation(
                    lambda: supabase.table("produtos")
                    .upsert(est_dict, on_conflict="codigo")
                    .execute()
                )

          if "Caixa" in sheets:
            df_c = pd.read_excel(uploaded_file, sheet_name="Caixa")
            for _, row in df_c.iterrows():
              desc = (
                  str(row.get("DESCRIÇÃO", "")).strip()
                  if pd.notna(row.get("DESCRIÇÃO"))
                  else ""
              )
              if desc and desc != "nan":
                tipo = (
                    str(row.get("TIPO", "Entrada")).strip()
                    if pd.notna(row.get("TIPO"))
                    else "Entrada"
                )
                if tipo not in ["Entrada", "Saída"]:
                  tipo = "Entrada"
                dt = row.get("DATA")
                data_str = (
                    str(dt)[:10] if pd.notna(dt) else str(datetime.date.today())
                )
                valor = (
                    float(
                        row.get("ENTRADA R$", 0)
                        if tipo == "Entrada"
                        else row.get("SAÍDA R$", 0)
                    )
                    if pd.notna(
                        row.get("ENTRADA R$")
                        if tipo == "Entrada"
                        else row.get("SAÍDA R$")
                    )
                    else 0.0
                )

                caixa_dict = {
                    "data_movimentacao": data_str,
                    "descricao": desc,
                    "tipo": tipo,
                    "valor": valor,
                }
                execute_supabase_operation(
                    lambda: supabase.table("caixa").insert(caixa_dict).execute()
                )
                total_caixa += 1

                cat = (
                    str(row.get("CATEGORIA", "")).strip()
                    if pd.notna(row.get("CATEGORIA"))
                    else ""
                )
                if cat == "Aporte" or "Empréstimo" in desc or "Aporte" in desc:
                  socio = (
                      "Renan"
                      if "Renan" in desc
                      else ("Ronald" if "Ronald" in desc else "Renan")
                  )
                  aporte_dict = {
                      "data_aporte": data_str,
                      "socio": socio,
                      "valor": valor,
                  }
                  execute_supabase_operation(
                      lambda: supabase.table("aportes")
                      .insert(aporte_dict)
                      .execute()
                  )
                  total_aportes += 1

          st.session_state["flash_success"] = (
              f"🎉 Importação Completa Concluída! {total_prods} bonés,"
              f" {total_vendas} vendas, {total_caixa} lançamentos e"
              f" {total_aportes} aportes!"
          )
          st.rerun()
        except Exception:
          st.error("🌐 Erro de Conexão com a Internet ao importar os dados.")

    except Exception as e:
      st.error(f"Erro ao processar o arquivo Excel: {e}")

# ==============================================================================
# ABA 7: GESTÃO DE DADOS & BACKUP
# ==============================================================================
elif menu == "💾 Gestão de Dados":
  st.subheader("💾 Gestão de Dados & Backup")
  st.caption(
      "Gerencie o banco de dados, faça downloads de segurança e restaure"
      " backups do sistema."
  )

  col_status, col_backup = st.columns(2)

  # 1. Status da Conexão
  with col_status:
    st.markdown("### 📌 Status da Conexão")

    # Teste de conexão dinâmico com o Supabase
    is_connected = False
    try:
      res_ping = (
          supabase.table("produtos")
          .select("count", count="exact")
          .limit(1)
          .execute()
      )
      is_connected = True
    except Exception:
      is_connected = False

    if is_connected:
      st.success("🟢 **Conectado ao Supabase (PostgreSQL Nuvem)**")
      st.caption(
          "Seus dados estão gravados na nuvem e imunes a reinícios do servidor."
      )
    else:
      st.error("🔴 **Desconectado do Supabase / Sem Conexão de Rede**")
      st.caption(
          "Não foi possível alcançar o servidor na nuvem. Verifique sua conexão"
          " com a internet."
      )

  # 2. Exportar Backup Geral em Excel
  with col_backup:
    st.markdown("### 💾 Exportar Backup Geral em Excel")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
      (
          df_produtos
          if not df_produtos.empty
          else pd.DataFrame(columns=[
              "codigo",
              "cor",
              "frase",
              "categoria",
              "custo",
              "qtd_estoque",
          ])
      ).to_excel(writer, sheet_name="Produtos", index=False)
      (
          df_vendas
          if not df_vendas.empty
          else pd.DataFrame(columns=[
              "codigo_bone",
              "cliente",
              "valor_venda",
              "custo_unitario",
              "forma_pagto",
              "data_venda",
          ])
      ).to_excel(writer, sheet_name="Vendas", index=False)
      (
          df_caixa
          if not df_caixa.empty
          else pd.DataFrame(
              columns=["data_movimentacao", "descricao", "tipo", "valor"]
          )
      ).to_excel(writer, sheet_name="Caixa", index=False)
      (
          df_aportes
          if not df_aportes.empty
          else pd.DataFrame(columns=["data_aporte", "socio", "valor"])
      ).to_excel(writer, sheet_name="Aportes", index=False)

    output.seek(0)

    st.download_button(
        label="💾 Baixar Todos os Dados em Excel (.xlsx)",
        data=output,
        file_name=(
            f"Backup_R2_Bones_{datetime.date.today().strftime('%Y_%m_%d')}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

  st.markdown("---")
  st.markdown("### ⚙️ Operações de Banco Supabase")
  st.info(
      "Seu banco de dados está sincronizado diretamente na nuvem do Supabase."
      " Todos os cadastros, vendas e edições são mantidos permanentemente."
  )
