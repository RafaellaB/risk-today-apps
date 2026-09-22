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
    carregar_dados_mare_cache,
)


# ==========================================
# CONFIGURAÇÕES
# ==========================================

FUSO_RECIFE = timezone("America/Recife")

ARQUIVO_HISTORICO = BASE_DIR / "historico_risco-final.csv"

MAPA_ESTACOES = {
    "261160614A": "Campina do Barreto",
    "261160618A": "Torreão", 
    "261160623A": "RECIFE - APAC",
    "261160609A": "Imbiribeira",
    "261160603A": "Dois Irmãos",
}


# ==========================================
# NORMALIZAÇÃO DE DADOS
# ==========================================

def preparar_chuva(df_chuva):
    """
    Prepara o arquivo diário bruto para o cálculo de VP.

    Compatível com dados que tenham:
    - nome ou nomeEstacao
    - valor ou valorMedida
    """
    df = df_chuva.copy()

    if "datahora" not in df.columns:
        return pd.DataFrame()

    df["datahora"] = pd.to_datetime(
        df["datahora"],
        errors="coerce",
    )

    df = df.dropna(subset=["datahora"]).copy()

    if "nomeEstacao" not in df.columns:
        if "nome" in df.columns:
            df = df.rename(columns={"nome": "nomeEstacao"})
        elif "codestacao" in df.columns:
            df["codestacao"] = df["codestacao"].astype(str).str.strip()
            df["nomeEstacao"] = df["codestacao"].map(MAPA_ESTACOES)
        else:
            df["nomeEstacao"] = None

    if "valorMedida" not in df.columns:
        if "valor" in df.columns:
            df["valorMedida"] = df["valor"]
        else:
            df["valorMedida"] = 0.0

    df["valorMedida"] = pd.to_numeric(
        df["valorMedida"],
        errors="coerce",
    ).fillna(0.0)

    df = df.dropna(subset=["nomeEstacao"]).copy()

    df = df[
        df["nomeEstacao"].isin(ESTACOES_DESEJADAS)
    ].copy()

    return df


# ==========================================
# CÁLCULO DO VP
# ==========================================

def calcular_vp_por_hora(df_chuva, data_alvo):
    """
    Calcula VP por estação e por hora.

    Fórmula preservada:
        VP = (chuva acumulada em 10 min × 6) + chuva acumulada em 2 h
    """
    df = preparar_chuva(df_chuva)

    if df.empty:
        return pd.DataFrame()

    df["data"] = df["datahora"].dt.strftime("%Y-%m-%d")

    df = df[df["data"] == data_alvo].copy()

    if df.empty:
        return pd.DataFrame()

    df = df.set_index("datahora").sort_index()

    resultados = []

    for estacao, grupo in df.groupby("nomeEstacao"):
        chuva_10min = grupo["valorMedida"].rolling("10min").sum()
        chuva_2h = grupo["valorMedida"].rolling("2h").sum()

        temp = pd.DataFrame(
            {
                "chuva_10min": chuva_10min,
                "chuva_2h": chuva_2h,
            }
        )

        agregado = temp.resample("h").last()

        agregado["VP"] = (
            agregado["chuva_10min"] * 6
        ) + agregado["chuva_2h"]

        agregado["nomeEstacao"] = estacao

        resultados.append(agregado)

    if not resultados:
        return pd.DataFrame()

    df_vp = pd.concat(resultados).reset_index()

    df_vp["data"] = df_vp["datahora"].dt.strftime("%Y-%m-%d")
    df_vp["hora_ref"] = df_vp["datahora"].dt.strftime("%H:%M:%S")

    return df_vp[
        [
            "data",
            "hora_ref",
            "nomeEstacao",
            "VP",
        ]
    ]


# ==========================================
# CÁLCULO E CLASSIFICAÇÃO DO RISCO
# ==========================================

def calcular_risco(df_vp, df_mare):
    """
    Junta VP e maré e aplica a regra de negócio:

    - AM_real: maré astronômica real, mantida no histórico
    - AM_calc: se AM_real < 1, usa 1 somente para calcular risco
    - Nivel_Risco_Valor = VP × AM_calc
    """
    if df_vp.empty or df_mare.empty:
        return pd.DataFrame()

    df = pd.merge(
        df_vp,
        df_mare,
        on=["data", "hora_ref"],
        how="left",
    )

    if df.empty:
        return pd.DataFrame()

    df["VP"] = pd.to_numeric(
        df["VP"],
        errors="coerce",
    ).fillna(0.0)

    df["AM"] = pd.to_numeric(
        df["AM"],
        errors="coerce",
    )

    df["AM_real"] = df["AM"]

    df["AM_calc"] = df["AM_real"].copy()

    df.loc[
        df["AM_calc"].notna()
        & (df["AM_calc"] < 1),
        "AM_calc",
    ] = 1.0

    df["Nivel_Risco_Valor"] = (
        df["VP"] * df["AM_calc"]
    ).fillna(0.0).round(2)

    df["Classificacao_Risco"] = pd.cut(
        df["Nivel_Risco_Valor"],
        bins=[-np.inf, 30, 50, 100, np.inf],
        labels=[
            "Baixo",
            "Moderado",
            "Moderado Alto",
            "Alto",
        ],
    )

    # A Aba 2 espera "AM".
    # AM permanece como maré real, enquanto AM_calc é somente auxiliar.
    return df[
        [
            "data",
            "hora_ref",
            "nomeEstacao",
            "VP",
            "AM",
            "AM_real",
            "AM_calc",
            "Nivel_Risco_Valor",
            "Classificacao_Risco",
        ]
    ]


# ==========================================
# HISTÓRICO
# ==========================================

def carregar_historico_existente():
    """
    Lê o histórico atual, se ele existir.
    """
    if not ARQUIVO_HISTORICO.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(
            ARQUIVO_HISTORICO,
            encoding="utf-8",
        )
    except (pd.errors.EmptyDataError, UnicodeDecodeError):
        return pd.DataFrame()


def consolidar_historico(df_novo):
    """
    Atualiza o arquivo histórico sem duplicar estação + data + hora.
    """
    df_historico = carregar_historico_existente()

    df_final = pd.concat(
        [df_historico, df_novo],
        ignore_index=True,
        sort=False,
    )

    if df_final.empty:
        return df_final

    df_final["data"] = df_final["data"].astype(str)
    df_final["hora_ref"] = df_final["hora_ref"].astype(str)

    df_final = df_final.drop_duplicates(
        subset=[
            "data",
            "hora_ref",
            "nomeEstacao",
        ],
        keep="last",
    )

    df_final = df_final.sort_values(
        by=[
            "data",
            "hora_ref",
            "nomeEstacao",
        ],
    )

    df_final.to_csv(
        ARQUIVO_HISTORICO,
        index=False,
        encoding="utf-8",
    )

    return df_final


# ==========================================
# PROCESSAMENTO PRINCIPAL
# ==========================================

def main():
    print("📊 Iniciando consolidação do histórico de risco.")

    hoje = datetime.now(FUSO_RECIFE).strftime("%Y-%m-%d")

    df_mare = carregar_dados_mare_cache(ARQUIVO_MARE_AM)

    if df_mare.empty:
        print(
            "ERRO: não foi possível carregar os dados de maré.",
            file=sys.stderr,
        )
        sys.exit(1)

    arquivos_chuva = sorted(
        BASE_DIR.glob("chuva_recife_*.csv")
    )

    if not arquivos_chuva:
        print(
            "Nenhum arquivo chuva_recife_YYYY-MM-DD.csv foi encontrado."
        )
        sys.exit(0)

    resultados = []

    for arquivo in arquivos_chuva:
        correspondencia = re.search(
            r"(\d{4}-\d{2}-\d{2})",
            arquivo.name,
        )

        if not correspondencia:
            print(f"Ignorando arquivo com nome inválido: {arquivo.name}")
            continue

        data_arquivo = correspondencia.group(1)

        # Regra D+1:
        # O arquivo do dia atual ainda está em preenchimento e não pode
        # ser incluído na Aba 2.
        if data_arquivo >= hoje:
            print(
                f"Pulando {arquivo.name}: "
                "dia atual ainda está em preenchimento."
            )
            continue

        try:
            print(f"Processando {arquivo.name}.")

            df_chuva = pd.read_csv(
                arquivo,
                encoding="utf-8",
            )

            df_vp = calcular_vp_por_hora(
                df_chuva,
                data_arquivo,
            )

            if df_vp.empty:
                print(
                    f"Sem dados suficientes para calcular VP "
                    f"em {data_arquivo}."
                )
                continue

            df_risco = calcular_risco(
                df_vp,
                df_mare,
            )

            if df_risco.empty:
                print(
                    f"Sem risco consolidado para {data_arquivo}."
                )
                continue

            resultados.append(df_risco)

        except Exception as erro:
            print(
                f"ERRO ao processar {arquivo.name}: {erro}",
                file=sys.stderr,
            )

    if not resultados:
        print(
            "Nenhum arquivo de dias anteriores gerou "
            "dados novos para o histórico."
        )
        sys.exit(0)

    df_novo = pd.concat(
        resultados,
        ignore_index=True,
    )

    df_final = consolidar_historico(df_novo)

    print(
        f"✅ Histórico consolidado com {len(df_final)} "
        f"registro(s): {ARQUIVO_HISTORICO.name}"
    )


if __name__ == "__main__":
    main()