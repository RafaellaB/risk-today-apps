import pandas as pd
import requests
from datetime import datetime, timedelta
import pytz
from pathlib import Path
from io import StringIO
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_HISTORICO = BASE_DIR / 'historico_risco-final.csv'
ARQUIVO_TEMPO_REAL = BASE_DIR / 'chuva_tempo_real.csv'
URL_ARQUIVO_MARE = 'https://raw.githubusercontent.com/RafaellaB/risco-hoje/main/tide/mare_calculada_hora_em_hora_ano-completo.csv'
ESTACOES_DESEJADAS = ["Campina do Barreto", "Torreão", "RECIFE - APAC", "Imbiribeira", "Dois Irmãos"]


MAPA_ESTACOES = {
    '261160614A': 'Campina do Barreto', 
    '261160609A': 'Torreão', 
    '261160623A': 'RECIFE - APAC', 
    '261160618A': 'Imbiribeira', 
    '261160603A': 'Dois Irmãos'
}


def consolidar_dia_anterior():
    fuso = pytz.timezone('America/Recife')
    ontem = datetime.now(fuso) - timedelta(days=1)
    data_alvo_str = ontem.strftime('%Y-%m-%d')
    
    print(f"Iniciando fechamento e consolidação do dia: {data_alvo_str}")

    # 1. Carrega dados de maré (para referência)
    try:
        resp_mare = requests.get(URL_ARQUIVO_MARE)
        linhas = [l for l in resp_mare.text.splitlines()
                  if not l.startswith(('<<<<', '====', '>>>>')) and l.strip()]
        df_am = pd.read_csv(
            StringIO("\n".join(linhas)),
            sep=';' if ';' in linhas[0] else ',',
            decimal=',',
            encoding='utf-8'
        )
        df_am = df_am.rename(
            columns={'Hora_Exata': 'datahora', 'Altura_m': 'AM',
                     'altura': 'AM', 'AM': 'AM'}
        )
        df_am['datahora'] = pd.to_datetime(
            df_am['datahora'].astype(str).str.split(';').str[0],
            errors='coerce'
        )
        df_am = df_am.dropna(subset=['datahora'])
        df_am['data'] = df_am['datahora'].dt.strftime('%Y-%m-%d')
        df_am['hora_ref'] = df_am['datahora'].dt.strftime('%H:00:00')
        df_am['AM'] = pd.to_numeric(
            df_am['AM'].astype(str).str.replace(',', '.'),
            errors='coerce'
        )
        df_am = df_am[['data', 'hora_ref', 'AM']]
    except Exception as e:
        print(f"Erro ao carregar maré: {e}")
        return

    # 2. Carrega os dados de chuva do arquivo temporário em tempo real
    if not ARQUIVO_TEMPO_REAL.exists():
        print("Arquivo `chuva_tempo_real.csv` não encontrado.")
        return

    try:
        df_chuva = pd.read_csv(ARQUIVO_TEMPO_REAL, encoding='utf-8')

        df_chuva['datahora'] = pd.to_datetime(
            df_chuva['datahora'], format='mixed', errors='coerce'
        )
        df_chuva = df_chuva.dropna(subset=['datahora'])

        # ← Mapear 'nome' via 'codestacao' (caso não esteja correto)
        if 'codestacao' in df_chuva.columns:
            df_chuva['codestacao'] = df_chuva['codestacao'].astype(str).str.strip()
            df_chuva['nome'] = df_chuva['codestacao'].map(MAPA_ESTACOES)

    except Exception as e:
        print(f"Erro ao ler chuva acumulada: {e}")
        return

    # 3. Filtrar dia anterior
    df_chuva['data'] = pd.to_datetime(df_chuva['datahora']).dt.date.astype(str)
    df_chuva = df_chuva[df_chuva['data'] == data_alvo_str].copy()

    if df_chuva.empty:
        print(f"Nenhum registro de chuva encontrado para o dia {data_alvo_str}")
        # Zera o arquivo, mantendo estrutura
        pd.DataFrame(
            columns=['datahora','codestacao','nome','valor',
                     'VP','AM','Nivel_Risco_Valor','Classificacao_Risco']
        ).to_csv(ARQUIVO_TEMPO_REAL, index=False)
        return

    # 4. Verificar se já tem risco calculado
    cols_risco = ['VP', 'AM', 'Nivel_Risco_Valor', 'Classificacao_Risco']
    if not all(c in df_chuva.columns for c in cols_risco):
        print(
            f"⚠️ AVISO: Dados do dia {data_alvo_str} não têm risco completo "
            "(VP/AM/Nivel_Risco_Valor/Classificacao_Risco). "
            "Será necessário recalcular."
        )
        # ← Fallback: calcular VP e risco (não deveria ocorrer normalmente)
        df_chuva = df_chuva.set_index('datahora').sort_index()
        resultados = []
        for estacao, grupo in df_chuva.groupby('nome'):
            temp_df = pd.DataFrame({
                'chuva_10min': grupo['valor'].rolling('10min').sum(),
                'chuva_2h': grupo['valor'].rolling('2h').sum()
            })
            agregado = temp_df.resample('h').last()
            agregado['VP'] = (agregado['chuva_10min'] * 6) + agregado['chuva_2h']
            agregado['nome'] = estacao
            resultados.append(agregado)

        df_vp = pd.concat(resultados).reset_index()
        df_vp['data'] = df_vp['datahora'].dt.strftime('%Y-%m-%d')
        df_vp['hora_ref'] = df_vp['datahora'].dt.strftime('%H:00:00')

        # Junta com maré e calcula risco
        df_final = pd.merge(df_vp, df_am, on=['data', 'hora_ref'], how='left')
        df_final['AM_real'] = df_final['AM']
        df_final['AM_calc'] = df_final['AM_real']
        aplicar_piso = pd.to_datetime(df_final['data']) >= pd.Timestamp('2026-05-01')
        df_final.loc[
            aplicar_piso &
            df_final['AM_calc'].notna() &
            (df_final['AM_calc'] < 1),
            'AM_calc'
        ] = 1
        df_final['Nivel_Risco_Valor'] = (
            df_final['VP'] * df_final['AM_calc']
        ).fillna(0)

        bins = [-float('inf'), 30, 50, 100, float('inf')]
        df_final['Classificacao_Risco'] = pd.cut(
            df_final['Nivel_Risco_Valor'],
            bins=bins,
            labels=['Baixo', 'Moderado', 'Moderado Alto', 'Alto']
        )

        df_novo_dia = df_final[
            ['data', 'hora_ref', 'nome', 'VP', 'AM_real',
             'Nivel_Risco_Valor', 'Classificacao_Risco']
        ].copy()
        df_novo_dia = df_novo_dia.rename(columns={'nome': 'nomeEstacao',
                                                  'AM_real': 'AM'})

    else:
        # ← DADOS JÁ CALCULADOS – APENAS MOVER PARA O HISTÓRICO
        print(
            f"✅ Dados do dia {data_alvo_str} já têm risco calculado. "
            "Apenas movendo para histórico."
        )

        # ← Extrair horas cheias por estação
        df_chuva['hora'] = pd.to_datetime(df_chuva['datahora']).dt.floor('h')
        df_chuva['data'] = df_chuva['datahora'].dt.strftime('%Y-%m-%d')
        df_chuva['hora_ref'] = df_chuva['datahora'].dt.strftime('%H:00:00')

        # ← Remover duplicatas por estação + hora
        df_24_horas = df_chuva.drop_duplicates(
            subset=['nome', 'data', 'hora_ref'],
            keep='last'
        )

        # ← Garantir nomeEstacao
        df_24_horas['nomeEstacao'] = df_24_horas['nome']

        # ← Selecionar colunas no formato do histórico
        colunas_historico = [
            'data', 'hora_ref', 'nomeEstacao', 'VP', 'AM',
            'Nivel_Risco_Valor', 'Classificacao_Risco'
        ]
        df_novo_dia = df_24_horas[colunas_historico].copy()

    # 5. Atualiza o arquivo historico_risco-final.csv
    if ARQUIVO_HISTORICO.exists():
        try:
            df_existente = pd.read_csv(ARQUIVO_HISTORICO)
            df_existente = df_existente[df_existente['data'] != data_alvo_str]
            df_atualizado = pd.concat([df_existente, df_novo_dia],
                                      ignore_index=True)
        except Exception:
            df_atualizado = df_novo_dia
    else:
        df_atualizado = df_novo_dia

    df_atualizado.sort_values(by=['data', 'hora_ref'], inplace=True)
    df_atualizado.to_csv(ARQUIVO_HISTORICO, index=False)
    print(
        f"✅ Histórico `historico_risco-final.csv` atualizado com sucesso "
        f"para o dia {data_alvo_str}! ({len(df_novo_dia)} registros)"
    )

    # 6. Reseta o arquivo de tempo real, mantendo últimas 3 horas
    agora = datetime.now(fuso)
    limite = agora - timedelta(hours=3)
    df_chuva['datahora_dt'] = pd.to_datetime(df_chuva['datahora'])
    df_manter = df_chuva[df_chuva['datahora_dt'] >= limite]

    pd.DataFrame(
        columns=['datahora','codestacao','nome','valor',
                 'VP','AM','Nivel_Risco_Valor','Classificacao_Risco']
    ).to_csv(ARQUIVO_TEMPO_REAL, index=False)

    if not df_manter.empty:
        df_manter[
            ['datahora','codestacao','nome','valor',
             'VP','AM','Nivel_Risco_Valor','Classificacao_Risco']
        ].to_csv(
            ARQUIVO_TEMPO_REAL,
            mode='a',
            header=True,
            index=False,
            encoding='utf-8'
        )
        print(
            f"🧹 Arquivo `chuva_tempo_real.csv` limpo, "
            f"mantendo últimas 3 horas ({len(df_manter)} registros)"
        )
    else:
        print(
            "🧹 Arquivo `chuva_tempo_real.csv` limpo e zerado "
            "para gravar apenas o novo dia."
        )


if __name__ == "__main__":
    consolidar_dia_anterior()