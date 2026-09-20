import os
import sys
import time
import pandas as pd
import requests
from datetime import datetime
from pytz import timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_TEMPO_REAL = BASE_DIR / 'chuva_tempo_real.csv'


def obter_token_cemaden():
    """Obtém o token de autenticação da API do CEMADEN."""
    email = os.getenv("CEMADEN_EMAIL")
    senha = os.getenv("CEMADEN_PASS")
    secrets_path = BASE_DIR / '.streamlit' / 'secrets.toml'
    if (not email or not senha) and secrets_path.exists():
        try:
            import tomllib
            with secrets_path.open('rb') as arquivo:
                secrets = tomllib.load(arquivo)
            email = email or secrets.get('CEMADEN_EMAIL')
            senha = senha or secrets.get('CEMADEN_PASS')
        except Exception:
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


    # Endpoint de DADOS RECENTES (brutos, múltiplas medições por estação)
    url_base = 'https://sws.cemaden.gov.br/PED/rest/pcds/pcds-dados-recentes'
    headers = {'token': token}
    lista_dfs = []


    print("Buscando dados recentes do CEMADEN estação por estação...")
    for codestacao in estacoes_de_recife:
        params = {
            'codestacao': codestacao,
            'rede': '11',
            'uf': 'PE',
            'formato': 'JSON',
        }
        sucesso_estacao = False
        for tentativa in range(1, 4):
            try:
                response = requests.get(url_base, headers=headers, params=params, timeout=30)
                if response.status_code == 200:
                    dados = response.json()
                    if isinstance(dados, dict) and 'Nenhum resultado foi encontrado' in dados.get('Info', ''):
                        sucesso_estacao = True
                        break
                    if dados:
                        dados_para_df = [dados] if isinstance(dados, dict) else dados
                        lista_dfs.append(pd.DataFrame(dados_para_df))
                    sucesso_estacao = True
                    break
            except Exception:
                if tentativa < 3:
                    time.sleep(2)
        if not sucesso_estacao:
            print(f"Aviso: Falha na estação {codestacao}.")


    if not lista_dfs:
        print("Nenhum dado retornado pela API nas estações.")
        return


    df_final = pd.concat(lista_dfs, ignore_index=True)
    if df_final.empty or 'datahora' not in df_final.columns:
        print("DataFrame vazio ou sem coluna de data/hora.")
        return


    # Tratamento de fuso horário para Recife
    df_final['datahora'] = pd.to_datetime(df_final['datahora'], errors='coerce', utc=True)
    df_final = df_final.dropna(subset=['datahora'])
    df_final['datahora'] = df_final['datahora'].dt.tz_convert('America/Recife').dt.strftime('%Y-%m-%d %H:%M:%S')


    if 'codestacao' in df_final.columns:
        df_final['codestacao'] = df_final['codestacao'].astype(str).str.strip()
        df_final['nomeEstacao'] = df_final['codestacao'].map(mapa_estacoes)


    if 'valorMedida' not in df_final.columns:
        for col_alt in ['valor', 'medida', 'valormedida']:
            if col_alt in df_final.columns:
                df_final['valorMedida'] = df_final[col_alt]
                break


    if 'valorMedida' not in df_final.columns:
        print("Resposta sem coluna de medição válida.")
        return


    df_final['valorMedida'] = pd.to_numeric(df_final['valorMedida'], errors='coerce')
    df_final = df_final[df_final['codestacao'].isin(estacoes_de_recife)].dropna(subset=['valorMedida'])


    tz_recife = timezone('America/Recife')
    agora = datetime.now(tz_recife)
    hoje_str = agora.strftime('%Y-%m-%d')


    df_final['data_temp'] = pd.to_datetime(df_final['datahora']).dt.strftime('%Y-%m-%d')
    df_hoje = df_final[df_final['data_temp'] == hoje_str].copy()
    df_hoje.drop(columns=['data_temp'], inplace=True)


    if df_hoje.empty:
        print("Nenhum dado encontrado para o dia de hoje.")
        return


    # --- GERENCIAMENTO DO ARQUIVO ÚNICO DO DIA ATUAL ---
    if ARQUIVO_TEMPO_REAL.exists():
        try:
            df_existente = pd.read_csv(ARQUIVO_TEMPO_REAL)
            if 'datahora' in df_existente.columns:
                df_existente['data_temp'] = pd.to_datetime(df_existente['datahora'], errors='coerce').dt.strftime('%Y-%m-%d')
                df_existente = df_existente[df_existente['data_temp'] == hoje_str]
                df_existente.drop(columns=['data_temp'], inplace=True)
            df_combinado = pd.concat([df_existente, df_hoje], ignore_index=True)
        except Exception:
            df_combinado = df_hoje
    else:
        df_combinado = df_hoje


    df_final_csv = df_combinado.drop_duplicates(subset=['codestacao', 'datahora'], keep='last')
    df_final_csv.to_csv(ARQUIVO_TEMPO_REAL, index=False, encoding='utf-8')
    print(f"✅ Arquivo `chuva_tempo_real.csv` atualizado com o endpoint correto! Total: {len(df_final_csv)} registros.")


if __name__ == "__main__":
    atualizar_chuva_tempo_real()
    