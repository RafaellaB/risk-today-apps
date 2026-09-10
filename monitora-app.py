import os
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta
import pytz
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from io import StringIO
import folium
from streamlit_folium import st_folium
import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Bibliotecas do Open-Meteo oficial
import openmeteo_requests
import requests_cache
from retry_requests import retry

st.set_page_config(
    layout="wide",
    page_title="Risco Hoje - Recife | Risk Today",
    page_icon="💧",
)

# --- INICIALIZAÇÃO DE ESTADO ---
if "bairro_selecionado" not in st.session_state:
    st.session_state["bairro_selecionado"] = None

# -----------------------------
# 1. CONSTANTES E CONFIGURAÇÕES
# -----------------------------
URL_BASE_CHUVAS = 'https://raw.githubusercontent.com/RafaellaB/risco-hoje/main/chuva_recife_' 
SUFIXO_ARQUIVO_CHUVAS = '.csv'
URL_ARQUIVO_MARE_AM = 'https://raw.githubusercontent.com/RafaellaB/risco-hoje/main/tide/mare_calculada_hora_em_hora_ano-completo.csv'
CSV_DELIMITADOR = ',' 
COLUNAS_NO_CSV_CHUVAS = ['datahora', 'nome', 'valor'] 
ARQUIVO_HISTORICO_LOCAL = BASE_DIR / 'historico_risco.csv'
COLUNAS_HISTORICO = ['data', 'hora_ref', 'nomeEstacao', 'VP', 'AM_real', 'AM_calc', 'Nivel_Risco_Valor', 'Classificacao_Risco']
DATA_INICIO_LOCAL = '2026-05-01'

ESTACOES_DESEJADAS = ["Campina do Barreto", "Torreão", "RECIFE - APAC", "Imbiribeira", "Dois Irmãos"]

COORDENADAS_ESTACOES = {
    "Campina do Barreto": [-8.013000, -34.881000],
    "Torreão": [-8.037000, -34.884000],
    "RECIFE - APAC": [-8.044910, -34.875180],
    "Imbiribeira": [-8.120975, -34.913983],
    "Dois Irmãos": [-8.018378, -34.947058]
}

# -----------------------------
# 2. IDIOMA, TEMA E ESTILO (CSS)
# -----------------------------
TRADUCOES = {
    "Português": {
        "config": "Configurações",
        "idioma": "Idioma / Language",
        "tema": "Tema",
        "tab_map": "🌍 RISCO HOJE",
        "tab_hist": "📊 DADOS HISTÓRICOS",
        "tab_pub": "📚 METODOLOGIA",
        "hero_badge": "Recife · Monitoramento",
        "hero_title": "RISCO DE ALAGAMENTO",
        "hero_subtitle": "Acompanhamento visual com uso de diagrama geométrico para risco de alagamentos na cidade do Recife ",
        "aguardando_dados": "Aguardando carregamento de dados do CEMADEN e Marinha...",
        "bairro_ativo": "Bairro ativo",
        "selecionar_estacao": "Selecionar estação",
        "chuva_24h": "Chuva 24h",
        "chuva_12h": "Chuva 12h",
        "mare_atual": "Maré Atual",
        "t_astronomica": "tábua astronômica",
        "legenda_api": "acumulado API CEMADEN",
        "legenda_local": "acumulado local",
        "titulo_umidade": "💧 Umidade do Solo Estimada por Perfil",
        "camada_sup": "Superficial",
        "camada_trans": "Transição",
        "camada_int": "Intermediária",
        "camada_prof": "Profunda",
        "desc_sup": "perfil 0-1 cm",
        "desc_trans": "perfil 1-3 cm",
        "desc_int": "perfil 3-9 cm",
        "desc_prof": "perfil 27-81 cm",
        "alerta_critico": "Situação crítica em {}. Recomendação: atenção imediata a áreas vulneráveis e vias de drenagem.",
        "alerta_atencao": "Situação de atenção em {}. O cenário merece acompanhamento contínuo.",
        "alerta_normal": "Situação normal em {}. Os indicadores atuais não sugerem risco elevado.",
        "titulo_diagrama": "Diagrama de Risco (Evolução)",
        "sem_dados_diagrama": "Ainda não há dados consolidados de hoje para formar o diagrama.",
        "base_metodo": "Como interpretar o Risco",
        "base_desc": "Os dados de chuva são integrados em tempo real do **CEMADEN**. A altura da maré utiliza a previsão astronômica da **Marinha do Brasil**. O risco é definido pela combinação desses dois fatores: 🟢 **Baixo** (seguro), 🟡 **Moderado a Moderado-Alto** (atenção ao sistema de drenagem) e 🔴 **Alto** (risco crítico para alagamentos).",
        "popup_risco": "Risco Atual",
        "em_breve_hist": "Em breve esta área exibirá séries temporais consolidadas e histórico de eventos para Recife.",
        "em_breve_pub": "Em breve esta área exibirá referências técnicas e publicações científicas relacionadas ao projeto Risco Hoje.",
        "eixo_x": "Chuva / VP",
        "eixo_y": "Maré (m)",
        "hora": "Hora",
        "risco": "Risco",
        "botao_hist": "Clique aqui para acessar o histórico dos diagramas desde 2025",
    },
    "English": {
        "config": "Settings",
        "idioma": "Language / Idioma",
        "tema": "Theme",
        "tab_map": "🌍 RISK MAP",
        "tab_hist": "📊 HISTORICAL DATA",
        "tab_pub": "📚 SCIENTIFIC PUBLICATIONS",
        "hero_badge": "Recife · Monitoring",
        "hero_title": "💧 RISK TODAY: Flood Monitoring System",
        "hero_subtitle": "Visual monitoring using geometric diagrams for flood risk in the city of Recife",
        "aguardando_dados": "Waiting for CEMADEN and Navy data to load...",
        "bairro_ativo": "Active neighborhood",
        "selecionar_estacao": "Select station",
        "chuva_24h": "Rain 24h",
        "chuva_12h": "Rain 12h",
        "mare_atual": "Current Tide",
        "t_astronomica": "astronomical tide",
        "legenda_api": "CEMADEN API accumulated",
        "legenda_local": "local accumulated",
        "titulo_umidade": "💧 Estimated Soil Moisture by Profile",
        "camada_sup": "Surface",
        "camada_trans": "Transition",
        "camada_int": "Intermediate",
        "camada_prof": "Deep",
        "desc_sup": "profile 0-1 cm",
        "desc_trans": "profile 1-3 cm",
        "desc_int": "profile 3-9 cm",
        "desc_prof": "profile 27-81 cm",
        "alerta_critico": "Critical situation in {}. Recommendation: immediate attention to vulnerable areas and drainage routes.",
        "alerta_atencao": "Warning situation in {}. The scenario deserves continuous monitoring.",
        "alerta_normal": "Normal situation in {}. Current indicators do not suggest high risk.",
        "titulo_diagrama": "Risk Diagram (Evolution)",
        "sem_dados_diagrama": "There are no consolidated data for today to form the diagram yet.",
        "base_metodo": "Risk Interpretation Guide",
        "base_desc": "Rainfall data is integrated in real-time from **CEMADEN**. Tide height uses the **Brazilian Navy**'s astronomical prediction. Risk is defined by the combination of these two factors: 🟢 **Low** (safe), 🟡 **Moderate to Moderate-High** (monitor drainage), and 🔴 **High** (critical risk of flooding).",
        "popup_risco": "Current Risk",
        "em_breve_hist": "This area will soon display consolidated time series and event history for Recife.",
        "em_breve_pub": "This area will soon display technical references and scientific publications related to the Risk Today project.",
        "eixo_x": "Rain / VP",
        "eixo_y": "Tide (m)",
        "hora": "Time",
        "risco": "Risk",
        "botao_hist": "Click here to access the diagram history since 2025",
    }
}

RISCO_UI = {
    "Português": {'Alto': 'Alto', 'Moderado Alto': 'Moderado Alto', 'Moderado': 'Moderado', 'Baixo': 'Baixo'},
    "English": {'Alto': 'High', 'Moderado Alto': 'Moderate High', 'Moderado': 'Moderate', 'Baixo': 'Low'}
}

if "idioma_ativo" not in st.session_state:
    st.session_state["idioma_ativo"] = "Português"
if "bairro_selecionado" not in st.session_state:
    st.session_state["bairro_selecionado"] = ESTACOES_DESEJADAS[0]

t = TRADUCOES[st.session_state["idioma_ativo"]]
is_dark = st.session_state.get("is_dark_theme", True)

css_theme = """
    :root {
        --bg-top: #182635;
        --bg-bottom: #0f1a28;
        --ink-900: #f4f8fc;
        --ink-700: #d8e4ef;
        --ink-500: #a7bcd0;
        --card: #213447;
        --card-soft: #1b2c3e;
        --line: #3b556d;
        --primary: #2e96d6;
        --primary-strong: #1f6f9f;
        --hero-bg: linear-gradient(135deg, #0f5f9d 0%, #177ab8 55%, #2491d1 100%);
        --app-bg: radial-gradient(circle at 10% 2%, rgba(46, 150, 214, 0.18), transparent 24%),
                 radial-gradient(circle at 92% 4%, rgba(43, 147, 72, 0.10), transparent 22%),
                 linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
        --mini-card-bg: linear-gradient(180deg, rgba(35, 53, 72, 0.98), rgba(30, 45, 61, 0.96));
        --tab-list-bg: rgba(31, 47, 63, 0.92);
        --hero-text: #f8fbff;
        --chart-font: #e2e8f0;
        --chart-grid: #3b556d;
    }
""" if is_dark else """
    :root {
        --bg-top: #f7f9fc;
        --bg-bottom: #eef3f8;
        --ink-900: #10233d;
        --ink-700: #344054;
        --ink-500: #667085;
        --card: #ffffff;
        --card-soft: #f8fafc;
        --line: #e2e8f0;
        --primary: #0d47a1;
        --primary-strong: #1f7ae0;
        --hero-bg: linear-gradient(135deg, #0d47a1 0%, #177ae0 100%);
        --app-bg: radial-gradient(circle at top left, rgba(34, 139, 230, 0.14), transparent 30%),
                 radial-gradient(circle at top right, rgba(0, 0, 0, 0.08), transparent 26%),
                 linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
        --mini-card-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(247, 250, 255, 0.9));
        --tab-list-bg: rgba(255, 255, 255, 0.64);
        --hero-text: #ffffff;
        --chart-font: #344054;
        --chart-grid: rgba(148,163,184,0.18);
    }
"""

st.markdown(
    "<style>\n" + css_theme + """
        .stApp {
            background: var(--app-bg);
            color: var(--ink-900);
        }
        .block-container { padding-top: 1rem; padding-bottom: 2rem; }
        .hero-shell {
            background: var(--hero-bg);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 28px;
            padding: 1.2rem 1.4rem;
            box-shadow: 0 18px 34px rgba(0, 0, 0, 0.24);
            backdrop-filter: blur(16px);
            margin-bottom: 1rem;
        }
        .hero-badge {
            display: inline-flex; align-items: center; gap: 0.45rem; border-radius: 999px;
            padding: 0.3rem 0.75rem; font-weight: 700; font-size: 0.82rem; color: #eef7ff;
            background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.18);
        }
        .hero-title {
            text-align: center; margin: 0.9rem 0 0.2rem; font-weight: 900; color: var(--hero-text);
            line-height: 1.02; font-size: clamp(1.9rem, 3.1vw, 3rem);
        }
        .hero-subtitle { text-align: center; margin: 0; color: rgba(248, 251, 255, 0.82); font-size: 0.98rem; }
        .risk-chip {
            display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.7rem;
            border-radius: 999px; font-size: 0.8rem; font-weight: 700; background: rgba(46, 150, 214, 0.18);
            color: var(--ink-900); margin-bottom: 0.4rem; border: 1px solid rgba(46, 150, 214, 0.28);
        }
        .mini-card {
            background: var(--mini-card-bg);
            border: 1px solid var(--line); border-radius: 14px; padding: 0.55rem 0.7rem;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.22); min-height: 72px;
        }
        .mini-label { font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 800; color: var(--ink-500); margin-bottom: 0.2rem; }
        .mini-value { font-size: 1.3rem; font-weight: 900; line-height: 1.1; color: var(--ink-900); }
        .mini-note { font-size: 0.76rem; color: var(--ink-700); margin-top: 0.1rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 0.45rem; padding: 0.3rem; background: var(--tab-list-bg); border: 1px solid var(--line); border-radius: 999px; }
        .stTabs [data-baseweb="tab"] p { color: var(--ink-700); font-weight: 600; }
        .stTabs [aria-selected="true"] { background: linear-gradient(135deg, var(--primary) 0%, var(--primary-strong) 100%); color: white; font-weight: 700; }
        .stSelectbox label { color: var(--ink-700) !important; font-weight: 700; }
        div[data-baseweb="select"] > div { background: var(--card); color: var(--ink-900); border-color: var(--line); }
        div[data-testid="stMetricLabel"] p { color: var(--ink-700); font-weight: 700; }
        div[data-testid="stMetricValue"] { font-size: 1.7rem; color: var(--ink-900); }
        .alert-critical { border-radius: 14px; border: 1px solid rgba(215, 38, 61, 0.34); background: rgba(215, 38, 61, 0.16); color: var(--ink-900); padding: 1rem; font-weight: 600; margin-bottom: 1rem;}
        .alert-warning { border-radius: 14px; border: 1px solid rgba(240, 140, 0, 0.34); background: rgba(240, 140, 0, 0.16); color: var(--ink-900); padding: 1rem; font-weight: 600; margin-bottom: 1rem;}
        .alert-success { border-radius: 14px; border: 1px solid rgba(43, 147, 72, 0.34); background: rgba(43, 147, 72, 0.16); color: var(--ink-900); padding: 1rem; font-weight: 600; margin-bottom: 1rem;}
        h4 { color: var(--ink-900); font-weight: 800; }
        div[data-testid="stPlotlyChart"] { background: var(--card-soft); border: 1px solid var(--line); border-radius: 16px; padding: 0.35rem; }
        div[data-testid="stExpander"] { background: var(--card); border: 1px solid var(--line); border-radius: 16px; }
        p, span, label { color: var(--ink-700); }
        
        /* Arredondar as bordas do mapa Folium e iframes */
        div[data-testid="st-folium-map"], iframe {
            border-radius: 16px;
            overflow: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 3. FUNÇÕES DE DADOS REAIS
# -----------------------------
def _mini_card(titulo: str, valor: str, nota: str = "") -> None:
    st.markdown(
        f"""
        <div class="mini-card">
            <div class="mini-label">{titulo}</div>
            <div class="mini-value">{valor}</div>
            <div class="mini-note">{nota}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

@st.cache_data(ttl=3600, show_spinner=False)
def obter_token_cemaden():
    try:
        email = st.secrets["CEMADEN_EMAIL"] if "CEMADEN_EMAIL" in st.secrets else os.getenv("CEMADEN_EMAIL")
        senha = st.secrets["CEMADEN_PASS"] if "CEMADEN_PASS" in st.secrets else os.getenv("CEMADEN_PASS")
    except Exception:
        email = os.getenv("CEMADEN_EMAIL")
        senha = os.getenv("CEMADEN_PASS")
        
    if not email or not senha: return None
        
    token_url = 'https://sgaa.cemaden.gov.br/SGAA/rest/controle-token/tokens'
    try:
        response = requests.post(token_url, json={'email': email, 'password': senha}, timeout=10)
        if response.status_code == 200: return response.json().get('token')
    except Exception: pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def carregar_acumulados_api_cemaden(token, codibge='2611606'):
    if not token: return pd.DataFrame()
    url = 'https://sws.cemaden.gov.br/PED/rest/pcds-acum/acumulados-recentes'
    headers = {'token': token}
    params = {'codibge': codibge, 'formato': 'JSON'}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            dados = response.json()
            if isinstance(dados, list) and dados: return pd.DataFrame(dados)
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def buscar_previsao_noaa_openmeteo(lat=-8.0539, lon=-34.8811):
    """Busca dados horários completos do modelo NOAA GFS via Open-Meteo"""
    try:
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=3, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ["temperature_2m", "precipitation_probability", "precipitation", "weather_code"],
            "models": "ncep_gfs_seamless",
            "timezone": "America/Recife",
            "forecast_days": 2,
        }
        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]
        
        hourly = response.Hourly()
        hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
        hourly_precipitation_probability = hourly.Variables(1).ValuesAsNumpy()
        hourly_precipitation = hourly.Variables(2).ValuesAsNumpy()
        hourly_weather_code = hourly.Variables(3).ValuesAsNumpy()

        df_hourly = pd.DataFrame({
            "date": pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left"
            ).tz_convert("America/Recife"),
            "temperature_2m": hourly_temperature_2m,
            "precipitation_probability": hourly_precipitation_probability,
            "precipitation": hourly_precipitation,
            "weather_code": hourly_weather_code
        })
        return df_hourly
    except Exception:
        return pd.DataFrame()

def interpretar_codigo_clima(codigo, probabilidade_chuva=0, volume_chuva=0.0, hora_atual=12, idioma="Português"):
    """Mapeia o código do tempo ajustando com base na chuva real, horário e idioma ativo"""
    eh_noite = hora_atual >= 18 or hora_atual < 6
    
    if probabilidade_chuva > 20 or volume_chuva > 0.1:
        if idioma == "English":
            return "🌧️", "Rain"
        return "🌧️", "Chuva"
        
    if codigo in [0]:
        if idioma == "English":
            return ("🌙" if eh_noite else "☀️"), ("Clear night" if eh_noite else "Clear sky")
        return ("🌙" if eh_noite else "☀️"), ("Noite limpa" if eh_noite else "Céu limpo")
        
    elif codigo in [1, 2]:
        if idioma == "English":
            return ("☁️🌙" if eh_noite else "⛅"), "Partly cloudy"
        return ("☁️🌙" if eh_noite else "⛅"), "Parcialmente nublado"
        
    elif codigo in [3]:
        if idioma == "English":
            return "☁️", "Cloudy"
        return "☁️", "Nublado"
        
    elif codigo in [45, 48]:
        if idioma == "English":
            return "🌫️", "Foggy"
        return "🌫️", "Nevoeiro"
        
    elif 51 <= codigo <= 67 or 80 <= codigo <= 82:
        if idioma == "English":
            return "🌧️", "Rain"
        return "🌧️", "Chuva"
        
    elif codigo >= 95:
        if idioma == "English":
            return "⛈️", "Thunderstorm"
        return "⛈️", "Tempestade"
    else:
        if idioma == "English":
            return ("🌙" if eh_noite else "☀️"), "Fair"
        return ("🌙" if eh_noite else "☀️"), "Bom"

@st.cache_data(ttl=300, show_spinner=False)
def buscar_umidade_openmeteo(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "soil_moisture_0_to_1cm",
            "soil_moisture_1_to_3cm",
            "soil_moisture_3_to_9cm",
            "soil_moisture_27_to_81cm"
        ],
        "forecast_days": 2,
        "timezone": "America/Recife"
    }
    try:
        resposta = requests.get(url, params=params, timeout=10)
        if resposta.status_code == 200: return resposta.json()
    except Exception: pass
    return None

def extrair_umidade_hora_atual(dados_json, datahora_alvo):
    if not dados_json or "hourly" not in dados_json: 
        return 0.0, 0.0, 0.0, 0.0
    try:
        df_umidade = pd.DataFrame(dados_json["hourly"])
        df_umidade['time'] = pd.to_datetime(df_umidade['time']).dt.tz_localize(None)
        
        if datahora_alvo.tzinfo is not None:
            alvo_utc = datahora_alvo.astimezone(pytz.utc).replace(tzinfo=None)
        else:
            alvo_utc = datahora_alvo.replace(tzinfo=None)
        
        df_umidade['diferenca'] = (df_umidade['time'] - alvo_utc).abs()
        registro_atual = df_umidade.sort_values(by='diferenca').iloc[0]
        
        sup = float(registro_atual["soil_moisture_0_to_1cm"])
        trans = float(registro_atual["soil_moisture_1_to_3cm"])
        inter = float(registro_atual["soil_moisture_3_to_9cm"])
        prof = float(registro_atual["soil_moisture_27_to_81cm"])
        
        return sup, trans, inter, prof
    except Exception:
        try:
            return (
                float(dados_json["hourly"]["soil_moisture_0_to_1cm"][0]),
                float(dados_json["hourly"]["soil_moisture_1_to_3cm"][0]),
                float(dados_json["hourly"]["soil_moisture_3_to_9cm"][0]),
                float(dados_json["hourly"]["soil_moisture_27_to_81cm"][0])
            )
        except Exception: 
            return 0.0, 0.0, 0.0, 0.0

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
        if not df_dia.empty: lista_dfs.append(df_dia)
    if not lista_dfs: return pd.DataFrame()
    return pd.concat(lista_dfs, ignore_index=True)

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

# -----------------------------
# CABEÇALHO: BANNER PRINCIPAL (OCUPA 100% DA LARGURA)
# -----------------------------
st.markdown(
    f"""
    <div class="hero-shell">
        <div class="hero-badge">{t['hero_badge']}</div>
        <div class="hero-title">{t['hero_title']}</div>
        <div class="hero-subtitle">{t['hero_subtitle']}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# CHAVES DE CONTROLE: IDIOMA E TEMA (ABAIXO DO BANNER, ALINHADAS À DIREITA)
# -----------------------------
_, ctrl_col1, ctrl_col2 = st.columns([7, 1.5, 1.5], vertical_alignment="center")

with ctrl_col1:
    is_english = st.toggle("🌐 PT / EN", value=(st.session_state.get("idioma_ativo", "Português") == "English"))
    novo_idioma = "English" if is_english else "Português"
    if novo_idioma != st.session_state.get("idioma_ativo", "Português"):
        st.session_state["idioma_ativo"] = novo_idioma
        st.rerun()

idioma_sel = st.session_state.get("idioma_ativo", "Português")
t = TRADUCOES[idioma_sel]

with ctrl_col2:
    is_dark_mode = st.toggle("⛅ / ⛈️", value=st.session_state.get("is_dark_theme", True))
    if is_dark_mode != st.session_state.get("is_dark_theme", True):
        st.session_state["is_dark_theme"] = is_dark_mode
        st.rerun()

is_dark = st.session_state.get("is_dark_theme", True)

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

tab_mapa, tab_hist, tab_pub = st.tabs([
    t['tab_map'],
    t['tab_hist'],
    t['tab_pub'],
])
# -----------------------------
# ABA PRINCIPAL (MAPA DE RISCO)
# -----------------------------
with tab_mapa:
    fuso = pytz.timezone('America/Recife') 
    agora = datetime.now(fuso)
    data_hoje_str = agora.strftime('%Y-%m-%d')

    df_am = carregar_dados_mare_cache(URL_ARQUIVO_MARE_AM)
    df_chuva_raw = carregar_dados_chuva_periodo_remoto(DATA_INICIO_LOCAL, data_hoje_str)
    df_final = pd.DataFrame()

    if not df_chuva_raw.empty and not df_am.empty:
        datas_processar = sorted(df_chuva_raw['datahora'].dt.strftime('%Y-%m-%d').dropna().unique())
        df_vp = processar_dados_chuva_simplificado(df_chuva_raw, datas_processar, ESTACOES_DESEJADAS)
        df_final = pd.merge(df_vp, df_am, on=['data', 'hora_ref'], how='left')

        df_final['AM_real'] = df_final['AM']
        df_final['AM_calc'] = df_final['AM_real']
        df_final.loc[df_final['AM_calc'].notna() & (df_final['AM_calc'] < 1), 'AM_calc'] = 1
        df_final['Nivel_Risco_Valor'] = (df_final['VP'] * df_final['AM_calc']).fillna(0)
        
        bins = [-np.inf, 30, 50, 100, np.inf]
        df_final['Classificacao_Risco'] = pd.cut(df_final['Nivel_Risco_Valor'], bins=bins, labels=['Baixo', 'Moderado', 'Moderado Alto', 'Alto'])

    if df_final.empty:
        st.warning(t['aguardando_dados'])
    else:
        if "bairro_selecionado" not in st.session_state or st.session_state["bairro_selecionado"] not in ESTACOES_DESEJADAS:
            st.session_state["bairro_selecionado"] = ESTACOES_DESEJADAS[0]
        bairro = st.session_state["bairro_selecionado"]

        df_hoje = df_final[df_final['data'] == data_hoje_str]
        historico_bairro = df_hoje[df_hoje['nomeEstacao'] == bairro].sort_values(by='hora_ref')
        
        if not historico_bairro.empty:
            registro_atual = historico_bairro.iloc[-1]
            mare_atual = registro_atual['AM_real']
            chuva_atual_vp = registro_atual['VP']
            risco_atual = registro_atual['Classificacao_Risco']
        else:
            mare_atual = 0.0
            chuva_atual_vp = 0.0
            risco_atual = 'Baixo'

        mapa_estacoes = {
            '261160614A': 'Campina do Barreto',
            '261160609A': 'Torreão',
            '261160623A': 'RECIFE - APAC',
            '261160618A': 'Imbiribeira',
            '261160603A': 'Dois Irmãos'
        }
        
        chuva_12h = 0.0
        chuva_24h = 0.0
        usou_api_cemaden = False
        
        token_api = obter_token_cemaden()
        if token_api:
            df_acumulados_api = carregar_acumulados_api_cemaden(token_api, codibge='2611606')
            if not df_acumulados_api.empty and 'codestacao' in df_acumulados_api.columns:
                df_acumulados_api['nomeEstacao'] = df_acumulados_api['codestacao'].map(mapa_estacoes)
                acumulados_bairro = df_acumulados_api[df_acumulados_api['nomeEstacao'] == bairro]
                
                if not acumulados_bairro.empty:
                    chuva_12h = float(acumulados_bairro['acc12hr'].iloc[0])
                    chuva_24h = float(acumulados_bairro['acc24hr'].iloc[0])
                    usou_api_cemaden = True

        if not usou_api_cemaden:
            df_raw_bairro = df_chuva_raw[df_chuva_raw['nomeEstacao'] == bairro]
            agora_naive = agora.replace(tzinfo=None)
            
            limite_24h = agora_naive - timedelta(hours=24)
            limite_12h = agora_naive - timedelta(hours=12)
            
            chuva_24h = float(df_raw_bairro[df_raw_bairro['datahora'] >= limite_24h]['valorMedida'].sum())
            chuva_12h = float(df_raw_bairro[df_raw_bairro['datahora'] >= limite_12h]['valorMedida'].sum())

        legenda_card = "acumulado API CEMADEN" if usou_api_cemaden else "acumulado local"

        # Coleta a previsão no ponto geográfico da estação selecionada.
        coord_atual = COORDENADAS_ESTACOES.get(bairro, [-8.05, -34.90])
        df_noaa = buscar_previsao_noaa_openmeteo(
            lat=coord_atual[0],
            lon=coord_atual[1]
        )
        
        html_prev_itens = ""
        temp_atual_str = "--°C"
        condicao_atual_str = "Carregando..." if idioma_sel == "Português" else "Loading..."
        icone_atual_str = "☀️"
        
        if not df_noaa.empty:
            agora_utc = pd.Timestamp.now(tz="America/Recife")
            df_noaa['diff'] = (df_noaa['date'] - agora_utc).abs()
            idx_atual = df_noaa['diff'].idxmin()
            
            temp_atual_str = f"{df_noaa.loc[idx_atual, 'temperature_2m']:.0f}°C"
            code_atual = df_noaa.loc[idx_atual, 'weather_code']
            prob_atual = df_noaa.loc[idx_atual, 'precipitation_probability']
            vol_atual = df_noaa.loc[idx_atual, 'precipitation']
            hora_atual_num = df_noaa.loc[idx_atual, 'date'].hour
            
            icone_atual_str, condicao_atual_str = interpretar_codigo_clima(code_atual, prob_atual, vol_atual, hora_atual_num, idioma_sel)
            
            # Exibe as 24 horas completas do dia
            for i in range(idx_atual, min(idx_atual + 24, len(df_noaa))):
                row = df_noaa.iloc[i]
                h_item = row['date'].hour
                hora_fmt = row['date'].strftime('%H:00')
                temp_item = f"{row['temperature_2m']:.0f}°C"
                
                prob_val = float(row['precipitation_probability']) if not pd.isna(row['precipitation_probability']) else 0.0
                vol_val = float(row['precipitation']) if not pd.isna(row['precipitation']) else 0.0
                
                prob_chuva_str = f"{int(prob_val)}%"
                vol_chuva_str = f"{vol_val:.1f} mm"
                
                ico_item, _ = interpretar_codigo_clima(row['weather_code'], prob_val, vol_val, h_item, idioma_sel)
                
                html_prev_itens += (
                    f'<div style="text-align: center; min-width: 60px; padding: 0 4px; display: inline-block;">'
                    f'<div style="font-size: 0.72rem; color: var(--ink-500); font-weight: 800; margin-bottom: 2px;">{hora_fmt}</div>'
                    f'<div style="font-size: 1.15rem; margin: 1px 0;">{ico_item}</div>'
                    f'<div style="font-size: 0.78rem; color: var(--ink-900); font-weight: 900;">{temp_item}</div>'
                    f'<div style="font-size: 0.68rem; color: #2e96d6; font-weight: 700; margin-top: 2px;">🌧️ {prob_chuva_str}</div>'
                    f'<div style="font-size: 0.62rem; color: var(--ink-500); font-weight: 600;">💧 {vol_chuva_str}</div>'
                    f'</div>'
                )
        else:
            msg_indisponivel = "Dados NOAA indisponíveis." if idioma_sel == "Português" else "NOAA data unavailable."
            html_prev_itens = f"<div style='color: var(--ink-500); font-size: 0.8rem;'>{msg_indisponivel}</div>"

        titulo_card_noaa = (
            f"{bairro} • Previsão NOAA"
            if idioma_sel == "Português"
            else f"{bairro} • NOAA Forecast"
        )

        # Layout do Topo com o Card Nativo Expandido e Rodapé Separado com Segurança
        col_widget, col_cards = st.columns([1.6, 2.4], gap="medium", vertical_alignment="center")
        
        with col_widget:
            st.markdown(
                f"""
                <div class="mini-card" style="padding: 0.6rem 0.9rem; display: flex; flex-direction: column; justify-content: space-between; min-height: 125px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div class="mini-label" style="display: flex; align-items: center; gap: 4px;">
                                {titulo_card_noaa}
                            </div>
                            <div style="display: flex; align-items: baseline; gap: 8px; margin-top: 1px;">
                                <span style="font-size: 1.45rem; font-weight: 900; color: var(--ink-900);">{temp_atual_str}</span>
                                <span style="font-size: 0.8rem; font-weight: 700; color: var(--ink-700);">{condicao_atual_str}</span>
                            </div>
                        </div>
                        <div style="font-size: 2.1rem; line-height: 1;">{icone_atual_str}</div>
                    </div>
                    <div style="display: flex; justify-content: flex-start; align-items: center; border-top: 1px solid var(--line); padding-top: 6px; margin-top: 4px; overflow-x: auto; gap: 8px; scrollbar-width: thin;">
                        {html_prev_itens}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            # Legenda técnica e frase de aviso com suporte bilíngue
            if idioma_sel == "Português":
                st.caption("Fonte: Modelo NOAA GFS (Open-Meteo). *Por se tratar de uma projeção numérica, podem ocorrer variações locais.*")
            else:
                st.caption("Source: NOAA GFS Model (Open-Meteo). *As this is a numerical forecast, local variations may occur.*")

        with col_cards:
            topo2, topo3, topo4, topo5 = st.columns(4, vertical_alignment="center")
            with topo2:
                st.selectbox(t['selecionar_estacao'], options=ESTACOES_DESEJADAS, key="bairro_selecionado")
            with topo3:
                _mini_card(t['chuva_24h'], f"{chuva_24h:.1f} mm", legenda_card)
            with topo4:
                _mini_card(t['chuva_12h'], f"{chuva_12h:.1f} mm", legenda_card)
            with topo5:
                _mini_card(t['mare_atual'], f"{mare_atual:.1f} m", t['t_astronomica'])
        
        st.markdown("<div style='height: 0.55rem;'></div>", unsafe_allow_html=True)
        st.markdown("---")

        # -------------------------------------------------------------
        # Disposição Lado a Lado: Análise à esquerda, Mapa à direita
        # -------------------------------------------------------------
        analise_col, mapa_col = st.columns([1.5, 1], gap="large")

        with analise_col:
            st.markdown(f"<h4>{t['titulo_umidade']}</h4>", unsafe_allow_html=True)
            
            dados_meteo = buscar_umidade_openmeteo(coord_atual[0], coord_atual[1])
            
            sup, trans, inter, prof = extrair_umidade_hora_atual(dados_meteo, agora)

            u1, u2, u3, u4 = st.columns(4)
            with u1:
                _mini_card(t['camada_sup'], f"{sup:.3f} m³/m³", t['desc_sup'])
            with u2:
                _mini_card(t['camada_trans'], f"{trans:.3f} m³/m³", t['desc_trans'])
            with u3:
                _mini_card(t['camada_int'], f"{inter:.3f} m³/m³", t['desc_int'])
            with u4:
                _mini_card(t['camada_prof'], f"{prof:.3f} m³/m³", t['desc_prof'])

            st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

            st.markdown(f"<h4>{t['titulo_diagrama']}</h4>", unsafe_allow_html=True)
            if not historico_bairro.empty:
                fig = go.Figure()

                lim_x = max(110, historico_bairro['VP'].max() * 1.2 if not historico_bairro.empty else 110)
                lim_y = 5
                x_grid, y_grid = np.arange(0, lim_x, 1), np.linspace(0, lim_y, 100)
                z_grid = np.array([x * y for y in y_grid for x in x_grid]).reshape(len(y_grid), len(x_grid))

                # Fundo do diagrama (mantido intacto)
                fig.add_trace(go.Heatmap(x=x_grid, y=y_grid, z=z_grid, colorscale=[[0, "#90EE90"], [0.3, "#FFD700"], [0.5, "#FFA500"], [1.0, "#D32F2F"]], showscale=False, zmin=0, zmax=100, hoverinfo="none"))

                # Linha de trajeto histórico (mantida intacta)
                fig.add_trace(go.Scatter(x=historico_bairro['VP'], y=historico_bairro['AM_real'], mode='lines', line=dict(color='black', width=1, dash='dash'), hoverinfo='none', showlegend=False))

                mapa_de_cores = {'Alto': '#D32F2F', 'Moderado Alto': '#FFA500', 'Moderado': '#FFC107', 'Baixo': '#4CAF50'}

                total_pontos = len(historico_bairro)

                # Loop para plotar os pontos com destaque diferenciado para os 2 últimos
                for idx, (_, ponto) in enumerate(historico_bairro.iterrows()):
                    cor_ponto = mapa_de_cores.get(ponto['Classificacao_Risco'], 'black')
                    risco_ui_str = RISCO_UI[idioma_sel].get(ponto['Classificacao_Risco'], ponto['Classificacao_Risco'])
                    
                    # Identifica se é um dos dois últimos pontos (penúltimo = hora passada, último = hora atual)
                    is_ultimos_dois = idx >= total_pontos - 2

                    # Configuração dinâmica de destaque visual sem alterar o cálculo
                    tamanho_bolinha = 14 if is_ultimos_dois else 8
                    opacidade_ponto = 1.0 if is_ultimos_dois else 0.45
                    largura_borda = 2.5 if is_ultimos_dois else 1
                    cor_borda = 'white' if (is_ultimos_dois and is_dark) else 'black'

                    fig.add_trace(
                        go.Scatter(
                            x=[ponto['VP']], 
                            y=[ponto['AM_real']], 
                            mode='markers',
                            marker=dict(
                                color=cor_ponto, 
                                size=tamanho_bolinha, 
                                opacity=opacidade_ponto,
                                line=dict(width=largura_borda, color=cor_borda)
                            ),
                            hoverinfo='text',
                            hovertext=f"<b>{t['hora']}:</b> {ponto['hora_ref']}<br><b>{t['risco']}:</b> {risco_ui_str}<br><b>VP:</b> {ponto['VP']:.2f}<br><b>AM:</b> {ponto['AM_real']:.2f}",
                            showlegend=False,
                        )
                    )

                chart_font_color = '#e2e8f0' if is_dark else '#344054'
                chart_grid_color = '#3b556d' if is_dark else 'rgba(148,163,184,0.18)'

                fig.update_layout(
                    xaxis_title=t['eixo_x'],
                    yaxis_title=t['eixo_y'],
                    margin=dict(l=40, r=40, t=40, b=40),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color=chart_font_color),
                    xaxis=dict(gridcolor=chart_grid_color, zeroline=False),
                    yaxis=dict(gridcolor=chart_grid_color, zeroline=False)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(t['sem_dados_diagrama'])

            with st.expander(t['base_metodo'], expanded=False):
                st.markdown(t['base_desc'])

        with mapa_col:
            st.markdown("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)
            
            if risco_atual == 'Alto':
                st.markdown(f"<div class='alert-critical'>{t['alerta_critico'].format(bairro)}</div>", unsafe_allow_html=True)
            elif risco_atual in ['Moderado Alto', 'Moderado']:
                st.markdown(f"<div class='alert-warning'>{t['alerta_atencao'].format(bairro)}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='alert-success'>{t['alerta_normal'].format(bairro)}</div>", unsafe_allow_html=True)
            
            st.markdown("<div style='margin-top: 80px;'></div>", unsafe_allow_html=True)
            m = folium.Map(location=[-8.05, -34.90], zoom_start=12, tiles='OpenStreetMap')
            
            riscos_atuais = df_hoje.groupby('nomeEstacao').last()['Classificacao_Risco'].to_dict()

            for estacao_nome, coords in COORDENADAS_ESTACOES.items():
                risco_estacao = riscos_atuais.get(estacao_nome, 'Baixo')
                
                if risco_estacao == 'Alto': icon_color = 'red'
                elif risco_estacao in ['Moderado Alto', 'Moderado']: icon_color = 'orange'
                else: icon_color = 'green'
                
                icone_tipo = 'info-sign' if estacao_nome == bairro else 'map-marker'
                risco_ui_str = RISCO_UI[idioma_sel].get(risco_estacao, risco_estacao)

                popup = folium.Popup(f"<b>{estacao_nome}</b><br>{t['popup_risco']}: {risco_ui_str}", max_width=250)
                folium.Marker(
                    location=coords,
                    icon=folium.Icon(color=icon_color, icon=icone_tipo),
                    popup=popup,
                    tooltip=estacao_nome
                ).add_to(m)

            mapa_interativo = st_folium(m, height=450, width="100%", returned_objects=["last_object_clicked"])
            
            if mapa_interativo and mapa_interativo.get("last_object_clicked"):
                lat_click = mapa_interativo["last_object_clicked"]["lat"]
                lon_click = mapa_interativo["last_object_clicked"]["lng"]
                
                estacao_clicada = min(
                    COORDENADAS_ESTACOES.keys(), 
                    key=lambda k: (COORDENADAS_ESTACOES[k][0] - lat_click)**2 + (COORDENADAS_ESTACOES[k][1] - lon_click)**2
                )
                
                if estacao_clicada != st.session_state.get("bairro_selecionado"):
                    st.session_state["bairro_selecionado"] = estacao_clicada
                    st.rerun()

# -----------------------------
# ABAS SECUNDÁRIAS 
# -----------------------------
with tab_hist:
    st.link_button(
        label=t["botao_hist"], 
        url="https://painel-diagrama-de-risco-f5n2bwurkppdppawqhqkmz.streamlit.app/",
        type="primary"
    )

with tab_pub:
    if idioma_sel == "Português":
        st.markdown("**Embasamento metodológico:**")
        st.markdown("[**Risco de Inundação e Alagamento: Uma Abordagem de Visualização Geométrica**](https://arandu.ufrpe.br/items/02fcdf72-754d-4615-bcbe-72b152c515c9)")
        st.markdown("🔹 *Estudo focado na modelagem geométrica e espacial para análise e mapeamento de risco de inundação e alagamento.*")
        st.markdown("Autor: Igor Gomes")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("[**Painel Interativo de Monitoramento de Risco de Alagamentos para a Cidade do Recife**](https://arandu.ufrpe.br/items/08489bec-0f03-4071-a0ef-563ae8ea54b8)")
        st.markdown("🔹 *Desenvolvimento de plataforma web que integra dados meteorológicos e maregráficos em tempo real para suporte a decisões.*")
        st.markdown("Autor: Rafaella Moura")
    else:
        st.markdown("**Methodological foundation:**")
        st.markdown("[**Flood and Inundation Risk: A Geometric Visualization Approach**](https://arandu.ufrpe.br/items/02fcdf72-754d-4615-bcbe-72b152c515c9)")
        st.markdown("🔹 *Research focused on geometric and spatial modeling for mapping flood and inundation risk areas.*")
        st.markdown("Autor: Igor Gomes")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("[**Interactive Flood Risk Monitoring Dashboard for the City of Recife**](https://arandu.ufrpe.br/items/08489bec-0f03-4071-a0ef-563ae8ea54b8)")
        st.markdown("🔹 *Development of an analytical web platform integrating meteorological and tidal data in real-time for decision support.*")
        st.markdown("Autor: Rafaella Moura")

# ==========================================
# RODAPÉ: INSTITUIÇÕES E PARCEIROS (UX FLUIDO)
# ==========================================
st.markdown("---")

def get_image_base64(path_str):
    img_path = Path(path_str)
    if img_path.exists():
        with open(img_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{encoded}"
    return ""

logo_ilika = get_image_base64(BASE_DIR / "logos/ilika.png")
logo_irrd = get_image_base64(BASE_DIR / "logos/irrd.png")
logo_ipecti = get_image_base64(BASE_DIR / "logos/ipecti.png")
logo_ufpe = get_image_base64(BASE_DIR / "logos/ufpe.png")
logo_ufrpe = get_image_base64(BASE_DIR / "logos/ufrpe.png")
logo_ifpe = get_image_base64(BASE_DIR / "logos/ifpe.png")
logo_geosere = get_image_base64(BASE_DIR / "logos/geosere.png")
logo_geospectral = get_image_base64(BASE_DIR / "logos/geospectralscience.png")

if idioma_sel == "Português":
    titulo_rodape = "Instituições e Parceiros:"
else:
    titulo_rodape = "Institutions and Partners:"

st.markdown(
    f"""
    <div style="background-color: #ffffff; padding: 24px; border-radius: 12px; margin-top: 40px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <p style="color: #1a1a1a; font-weight: 700; text-align: center; margin-bottom: 20px; font-size: 1.1rem;">
            {titulo_rodape}
        </p>
        <div style="display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 40px;">
            <img src="{logo_ilika}" style="height: 45px; width: auto; object-fit: contain;" alt="Ilika">
            <img src="{logo_irrd}" style="height: 45px; width: auto; object-fit: contain;" alt="IRRD">
            <img src="{logo_ipecti}" style="height: 45px; width: auto; object-fit: contain;" alt="IPECTI">
            <img src="{logo_ufpe}" style="height: 45px; width: auto; object-fit: contain;" alt="UFPE">
            <img src="{logo_ufrpe}" style="height: 45px; width: auto; object-fit: contain;" alt="UFRPE">
            <img src="{logo_geosere}" style="height: 45px; width: auto; object-fit: contain;" alt="Geosere">
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)