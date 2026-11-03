import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
from pytz import timezone

BASE_DIR = Path(__file__).resolve().parent
FUSO_RECIFE = timezone("America/Recife")

ESTACOES_CEMADEN = ["261160614A", "261160609A", "261160623A", "261160618A", "261160603A"]

MAPA_ESTACOES = {
    "261160614A": "Campina do Barreto", "261160614": "Campina do Barreto",
    "261160609A": "Imbiribeira", "261160609": "Imbiribeira",
    "261160623A": "RECIFE - APAC", "261160623": "RECIFE - APAC",
    "261160618A": "Torreão", "261160618": "Torreão",
    "261160603A": "Dois Irmãos", "261160603": "Dois Irmãos",
}

def obter_token(email, senha):
    if not email or not senha: return None
    url_token = "https://sgaa.cemaden.gov.br/SGAA/rest/controle-token/tokens"
    try:
        resposta = requests.post(url_token, json={"email": email, "password": senha}, timeout=30)
        resposta.raise_for_status()
        return resposta.json().get("token")
    except requests.RequestException as erro:
        print(f"ERRO ao obter token CEMADEN: {erro}", file=sys.stderr)
        return None

def buscar_dados_cemaden(token, estacoes):
    if not token: return pd.DataFrame()
    url_base = "https://sws.cemaden.gov.br/PED/rest/pcds/pcds-dados-recentes"
    cabecalhos = {"token": token}
    respostas = []

    for codestacao in estacoes:
        parametros = {"codestacao": codestacao, "uf": "PE", "rede": "11", "sensor": "10", "formato": "JSON"}
        try:
            resposta = requests.get(url_base, headers=cabecalhos, params=parametros, timeout=30)
            resposta.raise_for_status()
            dados = resposta.json()
            if isinstance(dados, dict):
                if "Nenhum resultado foi encontrado" in str(dados.get("Info", "")): continue
                dados = [dados]
            if dados: respostas.append(pd.DataFrame(dados))
        except requests.RequestException as erro:
            print(f"Aviso falha estação {codestacao}: {erro}", file=sys.stderr)

    if not respostas: return pd.DataFrame()
    df = pd.concat(respostas, ignore_index=True, sort=False)

    if "datahora" not in df.columns or "codestacao" not in df.columns:
        return pd.DataFrame()

    df["datahora"] = pd.to_datetime(df["datahora"], errors="coerce", utc=True).dt.tz_convert(FUSO_RECIFE)
    df = df.dropna(subset=["datahora"]).copy()
    df["codestacao"] = df["codestacao"].astype(str).str.strip()

    df["nome"] = df["codestacao"].map(MAPA_ESTACOES)
    df.loc[df["nome"].isna(), "nome"] = df["codestacao"].apply(lambda c: MAPA_ESTACOES.get(str(c).strip() + "A"))

    if "valorMedida" in df.columns and "valor" not in df.columns:
        df["valor"] = df["valorMedida"]
    elif "valorMedida" in df.columns and "valor" in df.columns:
        df["valor"] = df["valor"].fillna(df["valorMedida"])

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["datahora"] = df["datahora"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return df

def atualizar_csv_diario(df_novos, caminho_csv):
    caminho_csv = Path(caminho_csv)
    if caminho_csv.exists() and caminho_csv.stat().st_size > 0:
        try:
            df_existente = pd.read_csv(caminho_csv, encoding="utf-8")
            df_combinado = pd.concat([df_existente, df_novos], ignore_index=True, sort=False)
        except Exception:
            df_combinado = df_novos.copy()
    else:
        df_combinado = df_novos.copy()

    df_combinado["datahora"] = pd.to_datetime(df_combinado["datahora"], errors="coerce")
    df_combinado = df_combinado.dropna(subset=["datahora", "codestacao"]).copy()
    df_combinado["codestacao"] = df_combinado["codestacao"].astype(str).str.strip()
    df_combinado = df_combinado.drop_duplicates(subset=["codestacao", "datahora"], keep="last")
    df_combinado = df_combinado.sort_values(by=["datahora", "codestacao"])
    df_combinado["datahora"] = df_combinado["datahora"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df_combinado.to_csv(caminho_csv, index=False, encoding="utf-8")
    print(f"✅ {caminho_csv.name} atualizado com {len(df_combinado)} registro(s).")

def main():
    print("🌧️ Iniciando coleta incremental de chuva.")
    email = os.getenv("CEMADEN_EMAIL")
    senha = os.getenv("CEMADEN_PASS")
    token = obter_token(email, senha)
    if not token: sys.exit(1)

    df_chuva_recente = buscar_dados_cemaden(token, ESTACOES_CEMADEN)
    if df_chuva_recente.empty:
        print("Nenhum dado recente foi retornado.")
        sys.exit(0)

    agora = datetime.now(FUSO_RECIFE)
    data_hoje = agora.strftime("%Y-%m-%d")
    data_ontem = (agora - timedelta(days=1)).strftime("%Y-%m-%d")

    df_chuva_recente["data_ref"] = pd.to_datetime(df_chuva_recente["datahora"]).dt.strftime("%Y-%m-%d")

    for data_ref in [data_hoje, data_ontem]:
        df_dia = df_chuva_recente[df_chuva_recente["data_ref"] == data_ref].copy()
        if df_dia.empty: continue
        df_dia = df_dia.drop(columns=["data_ref"], errors="ignore")
        atualizar_csv_diario(df_dia, BASE_DIR / f"chuva_recife_{data_ref}.csv")

    print("🚀 Coleta incremental concluída.")

if __name__ == "__main__":
    main()