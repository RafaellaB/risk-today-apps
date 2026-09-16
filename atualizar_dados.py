import os
import sys
import time
import pandas as pd
import requests
from datetime import datetime
from pytz import timezone
from pathlib import Path
from io import StringIO

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_TEMPO_REAL = BASE_DIR / 'chuva_tempo_real.csv'

def obter_token_cemaden():
    """Obtém o token de autenticação da API do CEMADEN."""
    email = os.getenv("CEMADEN_EMAIL")
    senha = os.getenv("CEMADEN_PASS")
    secrets_path = BASE_DIR / '.streamlit' / 'secrets.toml'
    if (not email or not senha) and secrets_path.exists():
        try:
            with secrets_path.open('rb') as arquivo:
                secrets = tomllib.load(arquivo)
            email = email or secrets.get('CEMADEN_EMAIL')
            senha = senha or secrets.get('CEMADEN_PASS')
        except (OSError, tomllib.TOMLDecodeError):
            pass
    if not email or not senha:
        return None
    try:
        token_url = 'https://sgaa.cemaden.gov.br/SGAA/rest/controle-token/tokens'
        login = {'email': email, 'password': senha}
        response = requests.post(token_url, json=login, timeout=15)
        if response.status_code == 200:
            return response.json().get('token')
    except Exception:
        pass
    return None

def atualizar_chuva_tempo_real():
    token = obter_token_cemaden()
    if not token:
        print("Erro: Não foi possível obter o token de acesso do CEMADEN.")
        return

    estacoes_de_recife = ['261160614A', '261160609A', '261160623A', '261160618A', '261160603A']
    mapa_estacoes = {
        '261160614A': 'Campina do Barreto',
        '261160609A': 'Torreão',
        '261160623A': 'RECIFE - APAC',
        '261160618A': 'Imbiribeira',
        '261160603A': 'Dois Irmãos'
    }

    # Utiliza o endpoint de acumulados recentes (formato CSV) que traz a série consolidada do dia
    url_acumulados = 'https://sws.cemaden.gov.br/PED/rest/pcds-acum/acumulados-recentes'
    headers = {'token': token}
    params = {'codibge': '2611606', 'formato': 'CSV'}

    print("Buscando dados acumulados recentes do CEMADEN para Recife...")
    try:
        response = requests.get(url_acumulados, headers=headers, params=params, timeout=20)
        if response.status_code == 200 and response.text.strip():
            df_api = pd.read_csv(StringIO(response.text))
        else:
            print("Erro ao obter CSV de acumulados do CEMADEN.")
            return
    except Exception as e:
        print(f"Exceção ao requisitar acumulados do CEMADEN: {e}")
        return

    if df_api.empty:
        print("Nenhum dado retornado pela API de acumulados.")
        return

    # Padroniza colunas para o formato esperado pelo app (datahora, codestacao, valorMedida, nomeEstacao)
    if 'codestacao' in df_api.columns:
        df_api['codestacao'] = df_api['codestacao'].astype(str).str.strip()
        df_api['nomeEstacao'] = df_api['codestacao'].map(mapa_estacoes)

    if 'datahora' not in df_api.columns and 'dataHora' in df_api.columns:
        df_api.rename(columns={'dataHora': 'datahora'}, inplace=True)

    if 'valorMedida' not in df_api.columns:
        for col_alt in ['valor', 'medida', 'valormedida', 'acc1hr']:
            if col_alt in df_api.columns:
                df_api['valorMedida'] = df_api[col_alt]
                break

    if 'datahora' not in df_api.columns or 'valorMedida' not in df_api.columns:
        print("O retorno da API não possui as colunas esperadas de datahora ou valor.")
        return

    df_api['datahora'] = pd.to_datetime(df_api['datahora'], errors='coerce', utc=True)
    df_api = df_api.dropna(subset=['datahora'])
    df_api['datahora'] = df_api['datahora'].dt.tz_convert('America/Recife').dt.strftime('%Y-%m-%d %H:%M:%S')

    df_api['valorMedida'] = pd.to_numeric(df_api['valorMedida'], errors='coerce')
    df_api = df_api[df_api['codestacao'].isin(estacoes_de_recife)].dropna(subset=['valorMedida'])

    tz_recife = timezone('America/Recife')
    agora = datetime.now(tz_recife)
    hoje_str = agora.strftime('%Y-%m-%d')

    df_api['data_temp'] = pd.to_datetime(df_api['datahora']).dt.strftime('%Y-%m-%d')
    df_hoje = df_api[df_api['data_temp'] == hoje_str].copy()
    df_hoje.drop(columns=['data_temp'], inplace=True)

    if df_hoje.empty:
        print("Nenhum dado encontrado para o dia de hoje nos acumulados.")
        return

    # --- GERENCIAMENTO DE ARQUIVO ÚNICO ROTATIVO (Sem acumular vários CSVs por dia) ---
    if ARQUIVO_TEMPO_REAL.exists():
        try:
            df_existente = pd.read_csv(ARQUIVO_TEMPO_REAL)
            if 'datahora' in df_existente.columns:
                df_existente['data_temp'] = pd.to_datetime(df_existente['datahora'], errors='coerce').dt.strftime('%Y-%m-%d')
                # Mantém no arquivo apenas registros que pertençam ao dia de hoje (limpando resíduos antigos)
                df_existente = df_existente[df_existente['data_temp'] == hoje_str]
                df_existente.drop(columns=['data_temp'], inplace=True)
            df_combinado = pd.concat([df_existente, df_hoje], ignore_index=True)
        except Exception:
            df_combinado = df_hoje
    else:
        df_combinado = df_hoje

    # Remove duplicatas por estação e hora exata, salvando no arquivo único fixo
    df_final = df_combinado.drop_duplicates(subset=['codestacao', 'datahora'], keep='last')
    df_final.to_csv(ARQUIVO_TEMPO_REAL, index=False, encoding='utf-8')
    print(f"✅ Arquivo único `chuva_tempo_real.csv` atualizado com sucesso! Total: {len(df_final)} registros em {agora.strftime('%Y-%m-%d %H:%M:%S')}.")

if __name__ == "__main__":
    atualizar_chuva_tempo_real()