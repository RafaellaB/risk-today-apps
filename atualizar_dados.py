import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import requests
from pathlib import Path

# ==============================
# CONFIGURAÇÕES GERAIS
# ==============================

BASE_DIR = Path(__file__).parent
ARQUIVO_CHUVA = BASE_DIR / "chuva_tempo_real.csv"
ARQUIVO_MARE = BASE_DIR / "mare Astronomica.csv"

# Estações desejadas e nomes
ESTACOES_DESEJADAS = ['Campina do Barreto', 'Torreão', 'RECIFE - APAC', 'Imbiribeira', 'Dois Irmãos']
MAPA_ESTACOES = {
    '261160614A': 'Campina do Barreto',
    '261160609A': 'Torreão',
    '261160623A': 'RECIFE - APAC',
    '261160618A': 'Imbiribeira',
    '261160603A': 'Dois Irmãos'
}

# ==============================
# FUNÇÕES AUXILIARES
# ==============================

def obter_token_cemaden():
    """
    Obtém token de autenticação da API do CEMADEN.
    """
    url = "https://pluviometriace.cemaden.recife.pe.gov.br/pluviometriace/api/token"
    payload = {
        "username": "recife",
        "password": "recife123",
        "grant_type": "password",
        "client_id": "pluviometria-client"
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"Erro ao obter token: {e}")
        return None


def carregar_acumulados_api_cemaden(token):
    """
    Busca acumulados de chuva (12h e 24h) de todas as estações via API do CEMADEN.
    Retorna DataFrame com colunas: codestacao, nome, acc12hr, acc24hr, datahora_api
    """
    if not token:
        return pd.DataFrame()

    url_base = "https://pluviometriace.cemaden.recife.pe.gov.br/pluviometriace/api/Estacoes/GetUltimaMedicao"
    headers = {"Authorization": f"Bearer {token}"}

    registros = []
    agora = datetime.now()

    for cod_estacao in MAPA_ESTACOES.keys():
        try:
            params = {"codigoEstacao": cod_estacao}
            resp = requests.get(url_base, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            dados = resp.json()

            # Extrair campos relevantes
            acc12 = dados.get("acumulado12Horas") or 0.0
            acc24 = dados.get("acumulado24Horas") or 0.0
            datahora_str = dados.get("dataHora")  # ex: "2025-08-12T14:45:00Z"

            if datahora_str:
                # Remover 'Z' e converter para datetime
                datahora_str = datahora_str.replace("Z", "")
                datahora_dt = datetime.fromisoformat(datahora_str)
            else:
                datahora_dt = agora

            registros.append({
                "codestacao": cod_estacao,
                "nome": MAPA_ESTACOES[cod_estacao],
                "acc12hr": float(acc12),
                "acc24hr": float(acc24),
                "datahora_api": datahora_dt
            })
        except Exception as e:
            print(f"Aviso: Falha na estação {cod_estacao}.")
            continue

    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    return df


def carregar_dados_mare_cache(arquivo_mare):
    """
    Carrega dados da maré astronômica do arquivo CSV.
    """
    if not arquivo_mare.exists():
        print("Arquivo de maré não encontrado.")
        return pd.DataFrame()

    df = pd.read_csv(arquivo_mare, sep=";", decimal=",")
    df["data"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m-%d")
    df["hora_ref"] = df["hora"].astype(str).str.zfill(2) + ":00:00"
    return df


def carregar_dados_chuva_tempo_real():
    """
    Carrega dados brutos de chuva do CSV (se existir).
    """
    if not ARQUIVO_CHUVA.exists():
        return pd.DataFrame(columns=["datahora", "codestacao", "nome", "valor"])

    df = pd.read_csv(ARQUIVO_CHUVA)
    if "datahora" in df.columns:
        df["datahora"] = pd.to_datetime(df["datahora"])
    return df


def processar_dados_chuva_simplificado(df_chuva_raw, datas_processar, estacoes_desejadas):
    """
    Calcula VP acumulado (0–24h) por estação e por data/hora.
    """
    if df_chuva_raw.empty:
        return pd.DataFrame()

    registros = []
    mapa_inverso = {v: k for k, v in MAPA_ESTACOES.items()}

    for data_str in datas_processar:
        data_dt = pd.to_datetime(data_str)
        fim = data_dt + pd.Timedelta(days=1)

        for estacao in estacoes_desejadas:
            cod_estacao = mapa_inverso.get(estacao)
            if not cod_estacao:
                continue

            df_est = df_chuva_raw[
                (df_chuva_raw["codestacao"] == cod_estacao) &
                (df_chuva_raw["datahora"].dt.strftime("%Y-%m-%d") == data_str)
            ].copy()

            if df_est.empty:
                continue

            vp_acumulado = 0.0
            for _, row in df_est.iterrows():
                t_row = row["datahora"]
                janela_ini = t_row - pd.Timedelta(hours=24)
                janela = df_est[df_est["datahora"].between(janela_ini, t_row)]
                vp = janela["valor"].sum()
                vp_acumulado = max(vp_acumulado, vp)

            for _, row in df_est.iterrows():
                registros.append({
                    "data": data_str,
                    "hora_ref": row["datahora"].strftime("%H:00:00"),
                    "codestacao": cod_estacao,
                    "nome": estacao,
                    "VP": round(vp_acumulado, 2)
                })

    if not registros:
        return pd.DataFrame()

    df_vp = pd.DataFrame(registros)
    return df_vp


def calcular_risco(df_vp, df_am):
    """
    Calcula AM_real, Nivel_Risco_Valor e Classificacao_Risco.
    """
    if df_vp.empty or df_am.empty:
        return pd.DataFrame()

    df = pd.merge(df_vp, df_am, on=["data", "hora_ref"], how="left")
    if df.empty:
        return df

    df["AM_real"] = df["AM"]
    df["AM_calc"] = df["AM_real"].copy()
    df.loc[df["AM_calc"].notna() & (df["AM_calc"] < 1), "AM_calc"] = 1

    df["Nivel_Risco_Valor"] = (df["VP"] * df["AM_calc"]).fillna(0)

    bins = [-np.inf, 30, 50, 100, np.inf]
    df["Classificacao_Risco"] = pd.cut(
        df["Nivel_Risco_Valor"],
        bins=bins,
        labels=["Baixo", "Moderado", "Moderado Alto", "Alto"]
    )

    return df


def atualizar_chuva_tempo_real():
    """
    Função principal: atualiza o arquivo chuva_tempo_real.csv com dados recentes.
    """
    print("Buscando dados recentes do CEMADEN estação por estação...")

    # Carregar dados existentes
    if ARQUIVO_CHUVA.exists():
        df_final_csv = pd.read_csv(ARQUIVO_CHUVA)
        df_final_csv["datahora"] = pd.to_datetime(df_final_csv["datahora"])
        df_final_csv["datahora_dt"] = df_final_csv["datahora"].dt.tz_localize(None)
    else:
        df_final_csv = pd.DataFrame(columns=["datahora", "codestacao", "nome", "valor", "VP", "AM", "Nivel_Risco_Valor", "Classificacao_Risco"])
        df_final_csv["datahora"] = pd.to_datetime(df_final_csv["datahora"])
        df_final_csv["datahora_dt"] = pd.to_datetime(df_final_csv["datahora"]).dt.tz_localize(None)

    # Definir janela de atualização (últimas 48h)
    fuso = pytz.timezone("America/Recife")
    agora_utc = pd.Timestamp.utcnow().tz_localize("UTC")
    agora = agora_utc.astimezone(fuso)
    limite = agora - timedelta(hours=48)
    limite_naive = limite.tz_localize(None)  # ← garantir tz-naive

    # Filtrar apenas dados recentes do CSV existente
    if not df_final_csv.empty:
        df_final_csv = df_final_csv[df_final_csv["datahora_dt"] >= limite_naive]

    # Buscar novos dados da API
    token = obter_token_cemaden()
    df_acumulados = carregar_acumulados_api_cemaden(token)

    if df_acumulados.empty:
        print("Nenhum dado novo obtido da API.")
    else:
        # Converter datahora_api para tz-naive
        df_acumulados["datahora_api"] = pd.to_datetime(df_acumulados["datahora_api"]).dt.tz_localize(None)

        # Filtrar apenas dados dentro da janela
        df_novos = df_acumulados[df_acumulados["datahora_api"] >= limite_naive]

        if not df_novos.empty:
            # Renomear para bater com o CSV
            df_novos = df_novos.rename(columns={"datahora_api": "datahora", "acc24hr": "valor"})
            df_novos = df_novos[["datahora", "codestacao", "nome", "valor"]]

            # Concatenar com dados existentes
            df_final_csv = pd.concat([df_final_csv, df_novos], ignore_index=True)
            df_final_csv = df_final_csv.drop_duplicates(subset=["datahora", "codestacao"], keep="last")

    # Recalcular VP, AM e risco
    datas_processar = sorted(df_final_csv["datahora"].dt.strftime("%Y-%m-%d").dropna().unique())
    df_vp = processar_dados_chuva_simplificado(df_final_csv, datas_processar, ESTACOES_DESEJADAS)
    df_am = carregar_dados_mare_cache(ARQUIVO_MARE)
    df_final = calcular_risco(df_vp, df_am)

    if not df_final.empty:
        # Montar DataFrame final para salvar
        df_salvar = df_final[["data", "hora_ref", "codestacao", "nome", "VP", "AM", "Nivel_Risco_Valor", "Classificacao_Risco"]].copy()
        df_salvar["datahora"] = pd.to_datetime(df_salvar["data"] + " " + df_salvar["hora_ref"])
        df_salvar = df_salvar[["datahora", "codestacao", "nome", "VP", "AM", "Nivel_Risco_Valor", "Classificacao_Risco"]]

        # Concatenar com dados brutos (chuva)
        df_bruto = df_final_csv[["datahora", "codestacao", "nome", "valor"]].copy()
        df_final_csv = pd.merge(df_bruto, df_salvar, on=["datahora", "codestacao", "nome"], how="left")

    # Salvar
    df_final_csv = df_final_csv.drop(columns=["datahora_dt"], errors="ignore")
    df_final_csv.to_csv(ARQUIVO_CHUVA, index=False, encoding="utf-8")
    print(f"✅ Arquivo atualizado: {len(df_final_csv)} registros.")


if __name__ == "__main__":
    atualizar_chuva_tempo_real()