import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pytz import timezone

from utils import (
    BASE_DIR,
    ARQUIVO_MARE_AM,
    ESTACOES_DESEJADAS,
    mapear_nome_estacao,
    carregar_dados_mare_cache,
)

FUSO_RECIFE = timezone("America/Recife")
ARQUIVO_HISTORICO = BASE_DIR / "historico_risco-final.csv"

def preparar_chuva(df_chuva):
    df = df_chuva.copy()
    df.columns = df.columns.str.lower().str.strip()

    if "datahora" not in df.columns:
        return pd.DataFrame()

    df["datahora"] = pd.to_datetime(df["datahora"], errors="coerce")
    df = df.dropna(subset=["datahora"]).copy()

    col_valor = "valormedida" if "valormedida" in df.columns else ("valor" if "valor" in df.columns else None)
    if col_valor:
        if df[col_valor].dtype == "object":
            df["valorMedida"] = df[col_valor].astype(str).str.replace(",", ".", regex=False)
        else:
            df["valorMedida"] = df[col_valor]
        df["valorMedida"] = pd.to_numeric(df["valorMedida"], errors="coerce").fillna(0.0)
    else:
        df["valorMedida"] = 0.0

    if "codestacao" in df.columns:
        df["nomeEstacao"] = df["codestacao"].apply(mapear_nome_estacao)
    elif "nomeestacao" in df.columns:
        df["nomeEstacao"] = df["nomeestacao"].apply(mapear_nome_estacao)

    df = df.dropna(subset=["nomeEstacao"]).copy()
    df = df[df["nomeEstacao"].isin(ESTACOES_DESEJADAS)].copy()

    return df

def calcular_vp_por_hora(df_chuva, data_alvo):
    df = preparar_chuva(df_chuva)
    if df.empty: return pd.DataFrame()

    df["data"] = df["datahora"].dt.strftime("%Y-%m-%d")
    df = df[df["data"] == data_alvo].copy()
    if df.empty: return pd.DataFrame()

    df = df.set_index("datahora").sort_index()
    resultados = []

    for estacao, grupo in df.groupby("nomeEstacao"):
        chuva_10min = grupo["valorMedida"].rolling("10min").sum()
        chuva_2h = grupo["valorMedida"].rolling("2h").sum()

        temp = pd.DataFrame({"chuva_10min": chuva_10min, "chuva_2h": chuva_2h})
        agregado = temp.resample("h").last()
        agregado["VP"] = (agregado["chuva_10min"] * 6) + agregado["chuva_2h"]
        agregado["nomeEstacao"] = estacao
        resultados.append(agregado)

    if not resultados: return pd.DataFrame()

    df_vp = pd.concat(resultados).reset_index()
    df_vp["data"] = df_vp["datahora"].dt.strftime("%Y-%m-%d")
    df_vp["hora_ref"] = df_vp["datahora"].dt.strftime("%H:00:00")

    return df_vp[["data", "hora_ref", "nomeEstacao", "VP"]]

def calcular_risco(df_vp, df_mare):
    if df_vp.empty or df_mare.empty: return pd.DataFrame()
    df = pd.merge(df_vp, df_mare, on=["data", "hora_ref"], how="left")
    if df.empty: return pd.DataFrame()

    df["VP"] = pd.to_numeric(df["VP"], errors="coerce").fillna(0.0)
    df["AM"] = pd.to_numeric(df["AM"], errors="coerce")
    df["AM_real"] = df["AM"]
    df["AM_calc"] = df["AM_real"].copy()
    df.loc[df["AM_calc"].notna() & (df["AM_calc"] < 1), "AM_calc"] = 1.0

    df["Nivel_Risco_Valor"] = (df["VP"] * df["AM_calc"]).fillna(0.0).round(2)
    df["Classificacao_Risco"] = pd.cut(
        df["Nivel_Risco_Valor"],
        bins=[-np.inf, 30, 50, 100, np.inf],
        labels=["Baixo", "Moderado", "Moderado Alto", "Alto"],
    )

    return df[["data", "hora_ref", "nomeEstacao", "VP", "AM", "AM_real", "AM_calc", "Nivel_Risco_Valor", "Classificacao_Risco"]]

def carregar_historico_existente():
    if not ARQUIVO_HISTORICO.exists(): return pd.DataFrame()
    try:
        return pd.read_csv(ARQUIVO_HISTORICO, encoding="utf-8")
    except Exception:
        return pd.DataFrame()

def consolidar_historico(df_novo):
    df_historico = carregar_historico_existente()
    df_final = pd.concat([df_historico, df_novo], ignore_index=True, sort=False)
    if df_final.empty: return df_final

    df_final["data"] = df_final["data"].astype(str)
    df_final["hora_ref"] = df_final["hora_ref"].astype(str)
    df_final = df_final.drop_duplicates(subset=["data", "hora_ref", "nomeEstacao"], keep="last")
    df_final = df_final.sort_values(by=["data", "hora_ref", "nomeEstacao"])

    df_final.to_csv(ARQUIVO_HISTORICO, index=False, encoding="utf-8")
    return df_final

def main():
    print("📊 Iniciando consolidação do histórico de risco.")
    hoje = datetime.now(FUSO_RECIFE).strftime("%Y-%m-%d")
    df_mare = carregar_dados_mare_cache(ARQUIVO_MARE_AM)
    if df_mare.empty:
        print("ERRO ao carregar maré.", file=sys.stderr)
        sys.exit(1)

    arquivos_chuva = sorted(BASE_DIR.glob("chuva_recife_*.csv"))
    if not arquivos_chuva:
        print("Nenhum arquivo chuva_recife_YYYY-MM-DD.csv encontrado.")
        sys.exit(0)

    resultados = []
    for arquivo in arquivos_chuva:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", arquivo.name)
        if not m: continue
        data_arquivo = m.group(1)

        if data_arquivo >= hoje: continue

        try:
            df_chuva = pd.read_csv(arquivo, encoding="utf-8")
            df_vp = calcular_vp_por_hora(df_chuva, data_arquivo)
            if df_vp.empty: continue
            df_risco = calcular_risco(df_vp, df_mare)
            if df_risco.empty: continue
            resultados.append(df_risco)
        except Exception as erro:
            print(f"ERRO ao processar {arquivo.name}: {erro}", file=sys.stderr)

    if not resultados:
        print("Nenhum arquivo gerou dados novos.")
        sys.exit(0)

    df_novo = pd.concat(resultados, ignore_index=True)
    df_final = consolidar_historico(df_novo)
    print(f"✅ Histórico consolidado com {len(df_final)} registros.")

if __name__ == "__main__":
    main()