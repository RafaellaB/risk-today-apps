import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


import pandas as pd
import requests
from pytz import timezone



# ==========================================
# CONFIGURAÇÕES
# ==========================================


BASE_DIR = Path(__file__).resolve().parent


FUSO_RECIFE = timezone("America/Recife")


ESTACOES_CEMADEN = [
    "261160614A",
    "261160609A",
    "261160623A",
    "261160618A",
    "261160603A",
]


MAPA_ESTACOES = {
    "261160614A": "Campina do Barreto",
    "261160609A": "Imbiribeira",
    "261160623A": "RECIFE - APAC",
    "261160618A": "Torreão",
    "261160603A": "Dois Irmãos",
}



# ==========================================
# AUTENTICAÇÃO E CONSULTA À API
# ==========================================


def obter_token(email, senha):
    """
    Obtém o token de autenticação da API CEMADEN.


    As credenciais devem estar nos GitHub Secrets:
    - CEMADEN_EMAIL
    - CEMADEN_PASS
    """
    if not email or not senha:
        print(
            "ERRO: CEMADEN_EMAIL ou CEMADEN_PASS não foi encontrado.",
            file=sys.stderr,
        )
        return None


    url_token = "https://sgaa.cemaden.gov.br/SGAA/rest/controle-token/tokens"


    try:
        resposta = requests.post(
            url_token,
            json={
                "email": email,
                "password": senha,
            },
            timeout=30,
        )
        resposta.raise_for_status()


        token = resposta.json().get("token")


        if not token:
            print(
                "ERRO: A resposta de autenticação não contém o campo token.",
                file=sys.stderr,
            )
            return None


        print("✅ Token CEMADEN obtido com sucesso.")
        return token


    except requests.RequestException as erro:
        print(f"ERRO ao obter token CEMADEN: {erro}", file=sys.stderr)
        return None



def buscar_dados_cemaden(token, estacoes):
    """
    Busca dados recentes de chuva por estação no CEMADEN.


    O campo datahora fornecido pela API é tratado como UTC e convertido
    para America/Recife. O horário não é arredondado nem inventado.


    Exemplo:
    - API: 2026-09-21T23:40:00Z
    - CSV: 2026-09-21 20:40:00
    """
    if not token:
        return pd.DataFrame()


    url_base = "https://sws.cemaden.gov.br/PED/rest/pcds/pcds-dados-recentes"
    cabecalhos = {"token": token}
    respostas = []


    for codestacao in estacoes:
        parametros = {
            "codestacao": codestacao,
            "uf": "PE",
            "rede": "11",
            "sensor": "10",
            "formato": "JSON",
        }


        try:
            resposta = requests.get(
                url_base,
                headers=cabecalhos,
                params=parametros,
                timeout=30,
            )
            resposta.raise_for_status()


            dados = resposta.json()


            if isinstance(dados, dict):
                if "Nenhum resultado foi encontrado" in str(
                    dados.get("Info", "")
                ):
                    print(f"Aviso: sem dados para a estação {codestacao}.")
                    continue


                dados = [dados]


            if dados:
                respostas.append(pd.DataFrame(dados))
                print(
                    f"Estação {codestacao}: "
                    f"{len(dados)} registro(s) recebido(s)."
                )


        except requests.RequestException as erro:
            print(
                f"Aviso: falha ao consultar a estação {codestacao}: {erro}",
                file=sys.stderr,
            )


    if not respostas:
        return pd.DataFrame()


    df = pd.concat(respostas, ignore_index=True, sort=False)


    if "datahora" not in df.columns:
        print(
            "ERRO: a API não retornou a coluna datahora.",
            file=sys.stderr,
        )
        return pd.DataFrame()


    # utc=True evita qualquer conflito entre datetime tz-naive e tz-aware.
    df["datahora"] = pd.to_datetime(
        df["datahora"],
        errors="coerce",
        utc=True,
    ).dt.tz_convert(FUSO_RECIFE)


    df = df.dropna(subset=["datahora"]).copy()


    if "codestacao" not in df.columns:
        print(
            "ERRO: a API não retornou a coluna codestacao.",
            file=sys.stderr,
        )
        return pd.DataFrame()


    df["codestacao"] = df["codestacao"].astype(str).str.strip()


    # O nome usado pelo front atual é "nome".
    df["nome"] = df["codestacao"].map(MAPA_ESTACOES)


    # Grava como texto sem offset para preservar compatibilidade com o front.
    df["datahora"] = df["datahora"].dt.strftime("%Y-%m-%d %H:%M:%S")


    return df



# ==========================================
# ATUALIZAÇÃO DOS CSVs INCREMENTAIS
# ==========================================


def atualizar_csv_diario(df_novos, caminho_csv):
    """
    Une registros recebidos da API com o arquivo diário existente.


    A chave de deduplicação é:
    - codestacao
    - datahora


    Todas as colunas fornecidas pela API são preservadas.
    """
    caminho_csv = Path(caminho_csv)


    if caminho_csv.exists() and caminho_csv.stat().st_size > 0:
        try:
            df_existente = pd.read_csv(caminho_csv, encoding="utf-8")


            df_combinado = pd.concat(
                [df_existente, df_novos],
                ignore_index=True,
                sort=False,
            )
        except (pd.errors.EmptyDataError, UnicodeDecodeError) as erro:
            print(
                f"Aviso: não foi possível ler {caminho_csv.name}: {erro}. "
                "O arquivo será recriado."
            )
            df_combinado = df_novos.copy()
    else:
        df_combinado = df_novos.copy()


    if "datahora" not in df_combinado.columns:
        print(
            f"ERRO: {caminho_csv.name} não possui coluna datahora.",
            file=sys.stderr,
        )
        return


    df_combinado["datahora"] = pd.to_datetime(
        df_combinado["datahora"],
        errors="coerce",
    )


    df_combinado = df_combinado.dropna(
        subset=["datahora", "codestacao"]
    ).copy()


    df_combinado["codestacao"] = (
        df_combinado["codestacao"].astype(str).str.strip()
    )


    df_combinado = df_combinado.drop_duplicates(
        subset=["codestacao", "datahora"],
        keep="last",
    )


    df_combinado = df_combinado.sort_values(
        by=["datahora", "codestacao"],
    )


    df_combinado["datahora"] = df_combinado["datahora"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    df_combinado.to_csv(
        caminho_csv,
        index=False,
        encoding="utf-8",
    )


    print(
        f"✅ {caminho_csv.name} atualizado com "
        f"{len(df_combinado)} registro(s)."
    )



# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================


def main():
    print("🌧️ Iniciando coleta incremental de chuva.")


    email = os.getenv("CEMADEN_EMAIL")
    senha = os.getenv("CEMADEN_PASS")


    token = obter_token(email, senha)


    if not token:
        sys.exit(1)


    df_chuva_recente = buscar_dados_cemaden(
        token,
        ESTACOES_CEMADEN,
    )


    if df_chuva_recente.empty:
        print("Nenhum dado recente foi retornado pela API.")
        sys.exit(0)


    agora = datetime.now(FUSO_RECIFE)


    data_hoje = agora.strftime("%Y-%m-%d")
    data_ontem = (agora - timedelta(days=1)).strftime("%Y-%m-%d")


    df_chuva_recente["data_ref"] = pd.to_datetime(
        df_chuva_recente["datahora"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")


    # Atualiza D e D-1.
    # D alimentará a Aba 1.
    # D-1 será consolidado pelo workflow diário e alimentará a Aba 2.
    for data_ref in [data_hoje, data_ontem]:
        df_dia = df_chuva_recente[
            df_chuva_recente["data_ref"] == data_ref
        ].copy()


        if df_dia.empty:
            print(f"Nenhum registro retornado para {data_ref}.")
            continue


        df_dia = df_dia.drop(columns=["data_ref"], errors="ignore")


        arquivo_diario = BASE_DIR / f"chuva_recife_{data_ref}.csv"


        print(f"Atualizando dados de {data_ref}.")
        atualizar_csv_diario(df_dia, arquivo_diario)


    print("🚀 Coleta incremental concluída.")



if __name__ == "__main__":
    main()