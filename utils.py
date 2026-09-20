# backend e funções
import os
import pandas as pd
import numpy as np
import requests
import streamlit as st
import openmeteo_requests
import requests_cache
from retry_requests import retry
from io import StringIO
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


# Constantes de dados

SUFIXO_ARQUIVO_CHUVAS = '.csv'
ARQUIVO_MARE_AM = BASE_DIR / 'tide' / 'mare_calculada_hora_em_hora_ano-completo.csv'
CSV_DELIMITADOR = ',' 
COLUNAS_NO_CSV_CHUVAS = ['datahora', 'nome', 'valor'] 
ARQUIVO_HISTORICO_FINAL = BASE_DIR / 'historico_risco-final.csv'
ARQUIVO_TEMPO_REAL = BASE_DIR / 'chuva_tempo_real.csv'
DATA_INICIO_LOCAL = '2026-05-01'


ESTACOES_DESEJADAS = ["Campina do Barreto", "Torreão", "RECIFE - APAC", "Imbiribeira", "Dois Irmãos"]


# Mapeamento de estações para códigos CEMADEN
ESTACOES_CODIGOS_CEMADEN = {
    "Campina do Barreto": "261160614A",
    "Torreão": "261160609A",
    "RECIFE - APAC": "261160623A",
    "Imbiribeira": "261160618A",
    "Dois Irmãos": "261160603A",
}


COORDENADAS_ESTACOES = {
    "Campina do Barreto": [-8.013000, -34.881000],
    "Torreão": [-8.037000, -34.884000],
    "RECIFE - APAC": [-8.044910, -34.875180],
    "Imbiribeira": [-8.120975, -34.913983],
    "Dois Irmãos": [-8.018378, -34.947058]
}


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
def carregar_dados_recentes_api_cemaden(token, codestacao='261160614A'):
    """
    Carrega dados RECENTES (brutos, múltiplas medições) de UMA estação específica.
    Endpoint: /pcds/pcds-dados-recentes
    Usado para: alimentar o arquivo chuva_tempo_real.csv e cálculos horários
    """
    if not token: return pd.DataFrame()
    
    url = 'https://sws.cemaden.gov.br/PED/rest/pcds/pcds-dados-recentes'
    headers = {'token': token}
    params = {'codestacao': codestacao, 'formato': 'CSV'}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200 and response.text.strip():
            df = pd.read_csv(StringIO(response.text))
            return df
    except Exception as e:
        print(f"Erro ao carregar CSV do CEMADEN (dados recentes): {e}")
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def carregar_todas_estacoes_recentes(token):
    """
    Carrega dados RECENTES de TODAS as estações desejadas.
    Retorna DataFrame concatenado com coluna 'nomeEstacao' preenchida.
    Usado pela aba 1 (tempo real)
    """
    if not token: return pd.DataFrame()
    
    dfs_estacoes = []
    
    for nome_estacao, cod_estacao in ESTACOES_CODIGOS_CEMADEN.items():
        df = carregar_dados_recentes_api_cemaden(token, codestacao=cod_estacao)
        if not df.empty:
            df['nomeEstacao'] = nome_estacao
            dfs_estacoes.append(df)
    
    if dfs_estacoes:
        return pd.concat(dfs_estacoes, ignore_index=True)
    
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def carregar_acumulados_api_cemaden(token, codibge='2611606'):
    """
    Carrega dados ACUMULADOS (totais por estação) de TODAS as estações de uma cidade.
    Endpoint: /pcds-acum/acumulados-recentes
    Usado para: cards de acumulados 12h e 24h
    """
    if not token: return pd.DataFrame()
    
    url = 'https://sws.cemaden.gov.br/PED/rest/pcds-acum/acumulados-recentes'
    headers = {'token': token}
    params = {'codibge': codibge, 'formato': 'CSV'}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200 and response.text.strip():
            df = pd.read_csv(StringIO(response.text))
            return df
    except Exception as e:
        print(f"Erro ao carregar CSV do CEMADEN (acumulados): {e}")
    return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def buscar_previsao_noaa_openmeteo(lat=-8.0539, lon=-34.8811):
    try:
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=3, backoff_factor=0.2)
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
            "models": "ncep_gfs_seamless",
            "timezone": "America/Recife",
            "forecast_days": 2,
        }
        
        response = retry_session.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if "hourly" in data:
                hourly = data["hourly"]
                df_hourly = pd.DataFrame({
                    "date": pd.to_datetime(hourly["time"]).tz_localize("America/Recife", ambiguous="NaT", nonexistent="shift_forward"),
                    "temperature_2m": hourly["temperature_2m"],
                    "precipitation_probability": hourly["precipitation_probability"],
                    "precipitation": hourly["precipitation"],
                    "weather_code": hourly["weather_code"]
                })
                return df_hourly
    except Exception as e:
        print(f"Erro ao buscar NOAA para lat {lat}, lon {lon}: {e}")
        
    horas_dummy = pd.date_range(start=pd.Timestamp.now(tz="America/Recife"), periods=24, freq="h")
    return pd.DataFrame({
        "date": horas_dummy,
        "temperature_2m": [28.0] * 24,
        "precipitation_probability": [0.0] * 24,
        "precipitation": [0.0] * 24,
        "weather_code": [0] * 24
    })


def interpretar_codigo_clima(codigo, probabilidade_chuva=0, volume_chuva=0.0, hora_atual=12, idioma="Português"):
    import pytz
    eh_noite = hora_atual >= 18 or hora_atual < 6
    if probabilidade_chuva > 20 or volume_chuva > 0.1:
        return "🌧️", ("Rain" if idioma == "English" else "Chuva")
    if codigo in [0]:
        return ("🌙" if eh_noite else "☀️"), (("Clear night" if eh_noite else "Clear sky") if idioma == "English" else ("Noite limpa" if eh_noite else "Céu limpo"))
    elif codigo in [1, 2]:
        return ("☁️🌙" if eh_noite else "⛅"), "Partly cloudy" if idioma == "English" else "Parcialmente nublado"
    elif codigo in [3]:
        return "☁️", "Cloudy" if idioma == "English" else "Nublado"
    elif codigo in [45, 48]:
        return "🌫️", "Foggy" if idioma == "English" else "Nevoeiro"
    elif 51 <= codigo <= 67 or 80 <= codigo <= 82:
        return "🌧️", "Rain" if idioma == "English" else "Chuva"
    elif codigo >= 95:
        return "⛈️", "Thunderstorm" if idioma == "English" else "Tempestade"
    else:
        return ("🌙" if eh_noite else "☀️"), "Fair" if idioma == "English" else "Bom"


@st.cache_data(ttl=300, show_spinner=False)
def buscar_umidade_openmeteo(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ["soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm", "soil_moisture_3_to_9cm", "soil_moisture_27_to_81cm"],
        "forecast_days": 2, "timezone": "America/Recife"
    }
    try:
        resposta = requests.get(url, params=params, timeout=10)
        if resposta.status_code == 200: return resposta.json()
    except Exception: pass
    return None


def extrair_umidade_hora_atual(dados_json, datahora_alvo):
    import pytz
    if not dados_json or "hourly" not in dados_json: 
        return 0.0, 0.0, 0.0, 0.0
    try:
        df_umidade = pd.DataFrame(dados_json["hourly"])
        df_umidade['time'] = pd.to_datetime(df_umidade['time']).dt.tz_localize(None)
        alvo_utc = datahora_alvo.astimezone(pytz.utc).replace(tzinfo=None) if datahora_alvo.tzinfo else datahora_alvo.replace(tzinfo=None)
        df_umidade['diferenca'] = (df_umidade['time'] - alvo_utc).abs()
        reg = df_umidade.sort_values(by='diferenca').iloc[0]
        return float(reg["soil_moisture_0_to_1cm"]), float(reg["soil_moisture_1_to_3cm"]), float(reg["soil_moisture_3_to_9cm"]), float(reg["soil_moisture_27_to_81cm"])
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


@st.cache_data(show_spinner=False)
def carregar_dados_mare_cache(caminho_am_data):
    try:
        caminho_path = Path(caminho_am_data)
        if not caminho_path.exists():
            return pd.DataFrame()
        
        with open(caminho_path, 'r', encoding='utf-8') as f:
            conteudo = f.read()

        linhas = [l for l in conteudo.splitlines() if not l.startswith(('<<<<', '====', '>>>>')) and l.strip()]
        if not linhas: return pd.DataFrame()
        
        df = pd.read_csv(StringIO("\n".join(linhas)), sep=';' if ';' in linhas[0] else ',', decimal=',', encoding='utf-8')
        df = df.rename(columns={'Hora_Exata': 'datahora', 'datahora': 'datahora', 'Altura_m': 'AM', 'altura': 'AM', 'AM': 'AM'})
        df['datahora'] = pd.to_datetime(df['datahora'].astype(str).str.split(';').str[0], errors='coerce')
        df = df.dropna(subset=['datahora'])
        df['data'] = df['datahora'].dt.strftime('%Y-%m-%d')
        df['hora_ref'] = df['datahora'].dt.strftime('%H:00:00')
        df['AM'] = pd.to_numeric(df['AM'].astype(str).str.replace(',', '.'), errors='coerce')
        return df[['data', 'hora_ref', 'AM']]
    except: return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False) 
def carregar_dados_chuva_tempo_real():
    """Lê o arquivo rotativo único do dia atual"""
    if not ARQUIVO_TEMPO_REAL.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(ARQUIVO_TEMPO_REAL, encoding='utf-8')
        if 'valor' in df.columns and 'valorMedida' not in df.columns:
            df.rename(columns={'valor': 'valorMedida'}, inplace=True)
        if 'nome' in df.columns and 'nomeEstacao' not in df.columns:
            df.rename(columns={'nome': 'nomeEstacao'}, inplace=True)
        if 'codestacao' in df.columns:
            mapa_estacoes = {
                '261160614A': 'Campina do Barreto',
                '261160609A': 'Torreão',
                '261160623A': 'RECIFE - APAC',
                '261160618A': 'Imbiribeira',
                '261160603A': 'Dois Irmãos',
            }
            nomes_mapeados = df['codestacao'].astype(str).str.strip().map(mapa_estacoes)
            if 'nomeEstacao' not in df.columns:
                df['nomeEstacao'] = nomes_mapeados
            else:
                df['nomeEstacao'] = df['nomeEstacao'].fillna(nomes_mapeados)
        if 'valorMedida' in df.columns:
            df['valorMedida'] = pd.to_numeric(df['valorMedida'], errors='coerce')
            df = df.dropna(subset=['valorMedida'])
        df['datahora'] = pd.to_datetime(df['datahora'], format='mixed', errors='coerce')
        return df.dropna(subset=['datahora'])
    except Exception:
        return pd.DataFrame()


def processar_dados_chuva_simplificado(df_chuva, datas_desejadas, estacoes_desejadas):
    if df_chuva.empty: return pd.DataFrame()
    df = df_chuva[df_chuva['nomeEstacao'].isin(estacoes_desejadas)].copy()
    df['data'] = df['datahora'].dt.date.astype(str)
    df = df[df['data'].isin(datas_desejadas)]
    if df.empty: return pd.DataFrame()
    df = df.set_index('datahora').sort_index()
    resultados = []
    for estacao, grupo in df.groupby('nomeEstacao'):
        temp_df = pd.DataFrame({'chuva_10min': grupo['valorMedida'].rolling('10min').sum(), 'chuva_2h': grupo['valorMedida'].rolling('2h').sum()})
        agregado = temp_df.resample('h').last()
        agregado['VP'] = (agregado['chuva_10min'] * 6) + agregado['chuva_2h']
        agregado['nomeEstacao'] = estacao
        resultados.append(agregado)
    df_vp = pd.concat(resultados).reset_index()
    df_vp['data'] = df_vp['datahora'].dt.strftime('%Y-%m-%d')
    df_vp['hora_ref'] = df_vp['datahora'].dt.strftime('%H:00:00')
    return df_vp


@st.cache_data(show_spinner=False)
def carregar_historico_consolidado():
    """Carrega o historico_risco-final.csv usando estritamente o valor real da maré (AM)"""
    if not ARQUIVO_HISTORICO_FINAL.exists():
        return pd.DataFrame()
    
    df = pd.read_csv(ARQUIVO_HISTORICO_FINAL)
    df['data'] = pd.to_datetime(df['data']).dt.strftime('%Y-%m-%d')
    
    df['AM_real'] = df['AM']
    df['AM_calc'] = df['AM_real']
    aplicar_piso = pd.to_datetime(df['data']) >= pd.to_datetime(DATA_INICIO_LOCAL)
    df.loc[aplicar_piso & df['AM_calc'].notna() & (df['AM_calc'] < 1), 'AM_calc'] = 1
    
    df['Nivel_Risco_Valor'] = (df['VP'] * df['AM_calc']).fillna(0)
    
    bins = [-np.inf, 30, 50, 100, np.inf]
    df['Classificacao_Risco'] = pd.cut(df['Nivel_Risco_Valor'], bins=bins, labels=['Baixo', 'Moderado', 'Moderado Alto', 'Alto'])
    return df