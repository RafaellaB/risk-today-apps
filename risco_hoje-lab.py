import os
import pandas as pd
import requests
import numpy as np
from datetime import datetime, date, timedelta
import pytz 
import streamlit as st 
import plotly.graph_objects as go 
from io import StringIO

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 1. AMBIENTE DOS ARQUIVOS
URL_BASE_CHUVAS = 'https://raw.githubusercontent.com/RafaellaB/risco-hoje/main/chuva_recife_' 
SUFIXO_ARQUIVO_CHUVAS = '.csv'
URL_ARQUIVO_MARE_AM = 'https://raw.githubusercontent.com/RafaellaB/risco-hoje/main/tide/mare_calculada_hora_em_hora_ano-completo.csv'
CSV_DELIMITADOR = ',' 
COLUNAS_NO_CSV_CHUVAS = ['datahora', 'nome', 'valor'] 
ARQUIVO_HISTORICO_LOCAL = BASE_DIR / 'historico_risco.csv'
COLUNAS_HISTORICO = ['data', 'hora_ref', 'nomeEstacao', 'VP', 'AM_real', 'AM_calc', 'Nivel_Risco_Valor', 'Classificacao_Risco']
DATA_INICIO_LOCAL = '2026-05-01'
DATA_INICIO_LOCAL_FMT = pd.to_datetime(DATA_INICIO_LOCAL).strftime('%d/%m/%Y')

# DICIONÁRIO DE TRADUÇÕES
traducoes = {
    "Português": {
        "titulo_pagina": "Risco Hoje - Laboratório",
        "btn_atualizar": "Atualizar Dados",
        "btn_historico": "Ver Histórico",
        "titulo_diagrama": "Diagrama de Risco",
        "sub_calc": "Maré Calculada",
        "sub_real": "Maré Real",
        "texto_hist_local": "Histórico local",
        "texto_hist_vazio": "Ainda não há histórico local salvo.",
        "texto_versao": "Versão 0.2 a partir de {data} às 00:00:00",
        "texto_intervalo": "Selecionar intervalo",
        "texto_estacao": "Selecionar estação (opcional)",
        "texto_tabela": "Dados (tabela)",
        "texto_sidebar_hist": "Use o histórico local para ver o acumulado deste laboratório.",
        "formato_data_diagrama": "%d/%m/%Y",
        "msg_aguardando": "Aguardando dados de hoje",
        "msg_erro": "Erro ao processar. Tente atualizar.",
        "header_grafico": "Diagrama de Risco",
        "eixo_x": "Chuva (mm)",
        "eixo_y": "Maré (m)",
        "tempo": "Hora",
        "risco": "Risco",
        "sigla_chuva": "VP",
        "sigla_mare": "AM"
    },
    "English": {
        "titulo_pagina": "Risk Today - Laboratory",
        "btn_atualizar": "Update Data",
        "btn_historico": "View History",
        "titulo_diagrama": "Risk Diagram",
        "sub_calc": "Calculated Tide (with Floor AM_calc)",
        "sub_real": "Real Tide (No Floor AM_real)",
        "texto_hist_local": "Local history",
        "texto_hist_vazio": "No local history has been saved yet.",
        "texto_versao": "Version 0.2 starting from {data} at 00:00:00",
        "texto_intervalo": "Select interval",
        "texto_estacao": "Select station (optional)",
        "texto_tabela": "Data (table)",
        "texto_sidebar_hist": "Use local history to see this lab's accumulated data.",
        "formato_data_diagrama": "%Y-%m-%d",
        "msg_aguardando": "Waiting for today's data",
        "msg_erro": "Processing error. Please try updating.",
        "header_grafico": "Risk Diagram",
        "eixo_x": "Rainfall (mm)",
        "eixo_y": "Tide (m)",
        "tempo": "Time",
        "risco": "Risk",
        "sigla_chuva": "RVI",
        "sigla_mare": "THI"
    }
}

# 2. FUNÇÕES DE CACHE
@st.cache_data(show_spinner=False)
def carregar_dados_mare_cache(url_am_data):
    try:
        response = requests.get(url_am_data)
        if response.status_code != 200: return pd.DataFrame()
        linhas = [l for l in response.text.splitlines() if not l.startswith(('<<<<', '====', '>>>>')) and l.strip()]
        if not linhas: return pd.DataFrame()
        conteudo_limpo = "\n".join(linhas)
        separador = ';' if ';' in linhas[0] else ','
        df = pd.read_csv(StringIO(conteudo_limpo), sep=separador, decimal=',', encoding='utf-8')
        mapeamento = {'Hora_Exata': 'datahora', 'datahora': 'datahora', 'Altura_m': 'AM', 'altura': 'AM', 'AM': 'AM'}
        df = df.rename(columns=mapeamento)
        df['datahora'] = pd.to_datetime(df['datahora'].astype(str).str.split(';').str[0], errors='coerce')
        df = df.dropna(subset=['datahora'])
        df['data'] = df['datahora'].dt.strftime('%Y-%m-%d')
        df['hora_ref'] = df['datahora'].dt.strftime('%H:00:00')
        df['AM'] = pd.to_numeric(df['AM'].astype(str).str.replace(',', '.'), errors='coerce')
        return df[['data', 'hora_ref', 'AM']]
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False) 
def carregar_dados_chuva_cache(url_base, data_de_hoje_str, separador, colunas_csv):
    url_completa = f"{url_base}{data_de_hoje_str}{SUFIXO_ARQUIVO_CHUVAS}"
    try:
        df_chuva_raw = pd.read_csv(url_completa, encoding='utf-8', sep=separador)
        df_chuva_raw.rename(columns={'nome': 'nomeEstacao', 'valor': 'valorMedida'}, inplace=True)
        df_chuva_raw['datahora'] = pd.to_datetime(df_chuva_raw['datahora'])
        return df_chuva_raw
    except: return pd.DataFrame()

def carregar_dados_chuva_periodo_remoto(data_inicio_str, data_fim_str):
    data_inicio = pd.to_datetime(data_inicio_str)
    data_fim = pd.to_datetime(data_fim_str)
    lista_dfs = []

    for data_atual in pd.date_range(data_inicio, data_fim, freq='D'):
        data_str = data_atual.strftime('%Y-%m-%d')
        df_dia = carregar_dados_chuva_cache(URL_BASE_CHUVAS, data_str, CSV_DELIMITADOR, COLUNAS_NO_CSV_CHUVAS)
        if not df_dia.empty:
            lista_dfs.append(df_dia)

    if not lista_dfs:
        return pd.DataFrame()

    return pd.concat(lista_dfs, ignore_index=True)

# 3. FUNÇÕES DE PROCESSAMENTO
def processar_dados_chuva_simplificado(df_chuva, datas_desejadas, estacoes_desejadas):
    df = df_chuva[df_chuva['nomeEstacao'].isin(estacoes_desejadas)].copy()
    df['data'] = df['datahora'].dt.date.astype(str)
    df = df[df['data'].isin(datas_desejadas)]
    if df.empty: return pd.DataFrame()
    df = df.set_index('datahora').sort_index()
    resultados_por_estacao = []
    for estacao, grupo in df.groupby('nomeEstacao'):
        chuva_10min = grupo['valorMedida'].rolling('10min').sum()
        chuva_2h = grupo['valorMedida'].rolling('2h').sum()
        temp_df = pd.DataFrame({'chuva_10min': chuva_10min, 'chuva_2h': chuva_2h})
        agregado_horario = temp_df.resample('h').last()
        agregado_horario['VP'] = (agregado_horario['chuva_10min'] * 6) + agregado_horario['chuva_2h']
        agregado_horario['nomeEstacao'] = estacao
        resultados_por_estacao.append(agregado_horario)
    df_vp = pd.concat(resultados_por_estacao).reset_index()
    df_vp['data'] = df_vp['datahora'].dt.strftime('%Y-%m-%d')
    df_vp['hora_ref'] = df_vp['datahora'].dt.strftime('%H:00:00')
    return df_vp

def gerar_diagramas(df_analisado, idioma, key_prefix=""):
    t = traducoes[idioma]
    mapa_de_cores = {'Alto': '#D32F2F', 'Moderado Alto': '#FFA500', 'Moderado': '#FFC107', 'Baixo': '#4CAF50'}
    
    for (data, estacao), grupo in df_analisado.groupby(['data', 'nomeEstacao']):
        data_dt = pd.to_datetime(data, errors='coerce')
        if pd.isna(data_dt):
            data_formatada = str(data)
        else:
            data_formatada = data_dt.strftime(t['formato_data_diagrama'])

        st.subheader(f"{t['titulo_diagrama']}: {estacao} - {data_formatada}")
        
        # Criação das colunas lado a lado no Streamlit
        col_esquerda, col_direita = st.columns(2)
        grupo = grupo.sort_values(by='hora_ref')

        # Função auxiliar interna para gerar cada gráfico parametrizado
        def criar_figura(mare_col, usar_piso_no_risco=False):
            fig = go.Figure()
            lim_x = max(110, grupo['VP'].max() * 1.2 if not grupo.empty else 110)
            lim_y = 5 
            x_grid, y_grid = np.arange(0, lim_x, 1), np.linspace(0, lim_y, 100)
            z_grid = np.array([x * y for y in y_grid for x in x_grid]).reshape(len(y_grid), len(x_grid))
            
            # Fundo térmico (Matriz de Risco)
            fig.add_trace(go.Heatmap(
                x=x_grid, y=y_grid, z=z_grid, 
                colorscale=[[0, "#90EE90"], [0.3, "#FFD700"], [0.5, "#FFA500"], [1.0, "#D32F2F"]], 
                showscale=False, zmin=0, zmax=100, hoverinfo='none'
            ))
            
            # Linha tracejada conectando as horas do dia
            fig.add_trace(go.Scatter(
                x=grupo['VP'], y=grupo[mare_col], 
                mode='lines', line=dict(color='black', width=1, dash='dash'), 
                hoverinfo='none', showlegend=False
            ))
            
            # Marcadores de hora em hora
            for _, ponto in grupo.iterrows():
                if usar_piso_no_risco:
                    classe_risco = ponto['Classificacao_Risco']
                else:
                    # Recalcula o risco usando a Maré Real para ajustar a cor do ponto à sua posição física no heatmap
                    v_risco = ponto['VP'] * (ponto[mare_col] if pd.notna(ponto[mare_col]) else 0)
                    if v_risco <= 30: classe_risco = 'Baixo'
                    elif v_risco <= 50: classe_risco = 'Moderado'
                    elif v_risco <= 100: classe_risco = 'Moderado Alto'
                    else: classe_risco = 'Alto'

                cor_ponto = mapa_de_cores.get(classe_risco, 'black')
                
                fig.add_trace(go.Scatter(
                    x=[ponto['VP']], y=[ponto[mare_col]], 
                    mode='markers', 
                    marker=dict(color=cor_ponto, size=10, line=dict(width=1, color='black')),
                    hoverinfo='text',
                    hovertext=f"<b>{t['tempo']}:</b> {ponto['hora_ref']}<br>"
                              f"<b>{t['risco']}:</b> {classe_risco}<br>"
                              f"<b>{t['sigla_chuva']}:</b> {ponto['VP']:.2f}<br>"
                              f"<b>{t['sigla_mare']}:</b> {ponto[mare_col]:.2f}",
                    showlegend=False
                ))
            
            fig.update_layout(xaxis_title=t['eixo_x'], yaxis_title=t['eixo_y'], margin=dict(l=40, r=40, t=40, b=40))
            return fig

        # --- COLUNA DA ESQUERDA: AM_calc ---
        with col_esquerda:
            st.markdown(f"##### <center>{t.get('sub_calc', 'Maré Calculada (AM_calc)')}</center>", unsafe_allow_html=True)
            fig_calc = criar_figura('AM_calc', usar_piso_no_risco=True)
            st.plotly_chart(fig_calc, use_container_width=True, key=f"{key_prefix}calc_{data}_{estacao}")

        # --- COLUNA DA DIREITA: AM_real ---
        with col_direita:
            st.markdown(f"##### <center>{t.get('sub_real', 'Maré Real (AM_real)')}</center>", unsafe_allow_html=True)
            fig_real = criar_figura('AM_real', usar_piso_no_risco=False)
            st.plotly_chart(fig_real, use_container_width=True, key=f"{key_prefix}real_{data}_{estacao}")

def carregar_historico_local():
    if not os.path.exists(ARQUIVO_HISTORICO_LOCAL):
        return pd.DataFrame(columns=COLUNAS_HISTORICO)

    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_LOCAL)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=COLUNAS_HISTORICO)

    for coluna in COLUNAS_HISTORICO:
        if coluna not in df_historico.columns:
            df_historico[coluna] = np.nan

    return df_historico[COLUNAS_HISTORICO]

def salvar_historico_local(df_novo):
    df_historico = carregar_historico_local()
    df_para_salvar = df_novo.copy()

    colunas_saida = COLUNAS_HISTORICO
    for coluna in colunas_saida:
        if coluna not in df_para_salvar.columns:
            df_para_salvar[coluna] = np.nan

    df_para_salvar = df_para_salvar[colunas_saida]
    df_final = pd.concat([df_historico, df_para_salvar], ignore_index=True)
    df_final.drop_duplicates(subset=['data', 'hora_ref', 'nomeEstacao'], keep='last', inplace=True)
    df_final.sort_values(['data', 'hora_ref', 'nomeEstacao'], ascending=[False, False, True], inplace=True)
    df_final.to_csv(ARQUIVO_HISTORICO_LOCAL, index=False)
    return df_final

# BLOCO PRINCIPAL
if __name__ == "__main__":
    st.set_page_config(page_title="Risco Hoje - Laboratório / Risk Today - Laboratory", layout="wide")
    fuso = pytz.timezone('America/Recife') 
    data_hoje_str = datetime.now(fuso).strftime('%Y-%m-%d')

    # --- SIDEBAR ---
    idioma_sel = st.sidebar.radio("Idioma / Language", ["Português", "English"], horizontal=True, label_visibility="collapsed")
    t = traducoes[idioma_sel]
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button(t['btn_atualizar'], use_container_width=True, type="primary"):
        carregar_dados_chuva_cache.clear()
        st.rerun()

    st.sidebar.markdown("<br>"*12, unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.caption(t['texto_sidebar_hist'])

    # --- CONTEÚDO PRINCIPAL ---
    st.title(t['titulo_pagina'])
    st.divider()

    try:
        df_hist_local = carregar_historico_local()
        df_am = carregar_dados_mare_cache(URL_ARQUIVO_MARE_AM)
        df_chuva_raw = carregar_dados_chuva_periodo_remoto(DATA_INICIO_LOCAL, data_hoje_str)

        if not df_chuva_raw.empty and not df_am.empty:
            datas_processar = sorted(df_chuva_raw['datahora'].dt.strftime('%Y-%m-%d').dropna().unique())
            df_vp = processar_dados_chuva_simplificado(
                df_chuva_raw,
                datas_processar,
                ["Campina do Barreto", "Torreão", "RECIFE - APAC", "Imbiribeira", "Dois Irmãos"]
            )
            df_final = pd.merge(df_vp, df_am, on=['data', 'hora_ref'], how='left')

            df_final['AM_real'] = df_final['AM']

            df_final['AM_calc'] = df_final['AM_real']
            df_final.loc[df_final['AM_calc'].notna() & (df_final['AM_calc'] < 1), 'AM_calc'] = 1

            df_final['Nivel_Risco_Valor'] = (df_final['VP'] * df_final['AM_calc']).fillna(0)
            bins = [-np.inf, 30, 50, 100, np.inf]
            df_final['Classificacao_Risco'] = pd.cut(df_final['Nivel_Risco_Valor'], bins=bins, labels=['Baixo', 'Moderado', 'Moderado Alto', 'Alto'])

            df_hist_local = salvar_historico_local(df_final)

        st.subheader(t['texto_hist_local'])

        if df_hist_local.empty:
            st.info(t['texto_hist_vazio'])
        else:
            st.caption(t['texto_versao'].format(data=DATA_INICIO_LOCAL_FMT))

            col1, col2 = st.columns(2)
            with col1:
                datas_disponiveis = sorted(df_hist_local['data'].dropna().unique())
                data_min = pd.to_datetime(datas_disponiveis[0]).date()
                data_max = pd.to_datetime(datas_disponiveis[-1]).date()
                intervalo_datas = st.date_input(
                    t['texto_intervalo'],
                    value=(data_max, data_max),
                    min_value=data_min,
                    max_value=data_max,
                )
                if isinstance(intervalo_datas, tuple):
                    data_inicio_sel, data_fim_sel = intervalo_datas
                else:
                    data_inicio_sel = data_fim_sel = intervalo_datas
                data_inicio_sel = pd.to_datetime(data_inicio_sel).strftime('%Y-%m-%d')
                data_fim_sel = pd.to_datetime(data_fim_sel).strftime('%Y-%m-%d')

            with col2:
                estacoes_disponiveis = sorted(df_hist_local['nomeEstacao'].unique())
                estacoes_selecionadas = st.multiselect(
                    t['texto_estacao'],
                    options=estacoes_disponiveis,
                    default=estacoes_disponiveis
                )

            df_filtrado = df_hist_local[
                df_hist_local['data'].between(data_inicio_sel, data_fim_sel)
            ].copy()
            if estacoes_selecionadas:
                df_filtrado = df_filtrado[df_filtrado['nomeEstacao'].isin(estacoes_selecionadas)]

            if not df_filtrado.empty:
                with st.expander(t['texto_tabela'], expanded=False):
                    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
                gerar_diagramas(df_filtrado, idioma_sel, key_prefix="hist_")
            else:
                st.info("Nenhum dado disponível para a seleção.")
    except Exception as e:
        st.error(t['msg_erro'])