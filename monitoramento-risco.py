import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import streamlit as st
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import base64
from pathlib import Path


# Importações do módulo utils.py
from utils import (
    BASE_DIR,
    ARQUIVO_MARE_AM,
    DATA_INICIO_LOCAL,
    ESTACOES_DESEJADAS,
    COORDENADAS_ESTACOES,
    obter_token_cemaden,
    carregar_acumulados_api_cemaden,
    buscar_previsao_noaa_openmeteo,
    interpretar_codigo_clima,
    buscar_umidade_openmeteo,
    extrair_umidade_hora_atual,
    carregar_dados_mare_cache,
    carregar_dados_chuva_tempo_real,
    processar_dados_chuva_simplificado,
    carregar_historico_consolidado,
)


st.set_page_config(
    layout="wide",
    page_title="Risco Hoje",
    page_icon="📈",
)


if "bairro_selecionado" not in st.session_state:
    st.session_state["bairro_selecionado"] = None


# -----------------------------
# IDIOMA E ESTILO (CSS)
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
        "hero_subtitle": (
            "Acompanhamento visual com uso de diagrama geométrico "
            "para risco de alagamentos na cidade do Recife "
        ),
        "aguardando_dados": (
            "Aguardando carregamento de dados do CEMADEN e Marinha..."
        ),
        "selecionar_estacao": "Selecionar estação",
        "chuva_24h": "Chuva 24h",
        "chuva_12h": "Chuva 12h",
        "mare_atual": "Maré Atual",
        "t_astronomica": "tábua astronômica",
        "titulo_umidade": "Umidade do Solo Estimada por Perfil",
        "camada_sup": "Superficial",
        "camada_trans": "Transição",
        "camada_int": "Intermediária",
        "camada_prof": "Profunda",
        "desc_sup": "perfil 0-1 cm",
        "desc_trans": "perfil 1-3 cm",
        "desc_int": "perfil 3-9 cm",
        "desc_prof": "perfil 27-81 cm",
        "alerta_critico": (
            "Situação crítica em {}. Recomendação: atenção imediata a "
            "áreas vulneráveis e vias de drenagem."
        ),
        "alerta_atencao": (
            "Situação de atenção em {}. O cenário merece "
            "acompanhamento contínuo."
        ),
        "alerta_normal": (
            "Situação normal em {}. Os indicadores atuais não "
            "sugerem risco elevado."
        ),
        "titulo_diagrama": "Diagrama de Risco (Evolução)",
        "sem_dados_diagrama": (
            "Ainda não há dados consolidados para formar o diagrama."
        ),
        "base_metodo": "Como interpretar o Risco",
        "base_desc": (
            "Os dados de chuva são integrados em tempo real do "
            "**CEMADEN**. A altura da maré utiliza a previsão "
            "astronômica da **Marinha do Brasil**."
        ),
        "popup_risco": "Risco Atual",
        "eixo_x": "Chuva / VP",
        "eixo_y": "Maré (m)",
        "hora": "Hora",
        "risco": "Risco",
        "selecionar_data": "Selecionar Data do Histórico",
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
        "hero_subtitle": (
            "Visual monitoring using geometric diagrams for flood "
            "risk in the city of Recife"
        ),
        "aguardando_dados": (
            "Waiting for CEMADEN and Navy data to load..."
        ),
        "selecionar_estacao": "Select station",
        "chuva_24h": "Rain 24h",
        "chuva_12h": "Rain 12h",
        "mare_atual": "Current Tide",
        "t_astronomica": "astronomical tide",
        "titulo_umidade": "Estimated Soil Moisture by Profile",
        "camada_sup": "Surface",
        "camada_trans": "Transition",
        "camada_int": "Intermediate",
        "camada_prof": "Deep",
        "desc_sup": "profile 0-1 cm",
        "desc_trans": "profile 1-3 cm",
        "desc_int": "profile 3-9 cm",
        "desc_prof": "profile 27-81 cm",
        "alerta_critico": (
            "Critical situation in {}. Recommendation: immediate "
            "attention to vulnerable areas and drainage routes."
        ),
        "alerta_atencao": (
            "Warning situation in {}. The scenario deserves "
            "continuous monitoring."
        ),
        "alerta_normal": (
            "Normal situation in {}. Current indicators do not "
            "suggest high risk."
        ),
        "titulo_diagrama": "Risk Diagram (Evolution)",
        "sem_dados_diagrama": (
            "There are no consolidated data to form the diagram."
        ),
        "base_metodo": "Risk Interpretation Guide",
        "base_desc": (
            "Rainfall data is integrated in real-time from "
            "**CEMADEN**. Tide height uses the **Brazilian Navy**'s "
            "astronomical prediction."
        ),
        "popup_risco": "Current Risk",
        "eixo_x": "Rain / VP",
        "eixo_y": "Tide (m)",
        "hora": "Time",
        "risco": "Risk",
        "selecionar_data": "Select Historical Date",
    },
}


RISCO_UI = {
    "Português": {
        "Alto": "Alto",
        "Moderado Alto": "Moderado Alto",
        "Moderado": "Moderado",
        "Baixo": "Baixo",
    },
    "English": {
        "Alto": "High",
        "Moderado Alto": "Moderate High",
        "Moderado": "Moderate",
        "Baixo": "Low",
    },
}


if "idioma_ativo" not in st.session_state:
    st.session_state["idioma_ativo"] = "Português"

if "bairro_selecionado" not in st.session_state:
    st.session_state["bairro_selecionado"] = ESTACOES_DESEJADAS[0]


t = TRADUCOES[st.session_state["idioma_ativo"]]
is_dark = st.session_state.get("is_dark_theme", True)


css_theme = """
    :root {
        --bg-top: #182635; --bg-bottom: #0f1a28; --ink-900: #f4f8fc; --ink-700: #d8e4ef; --ink-500: #a7bcd0;
        --card: #213447; --card-soft: #1b2c3e; --line: #3b556d; --primary: #2e96d6; --primary-strong: #1f6f9f;
        --hero-bg: linear-gradient(135deg, #0f5f9d 0%, #177ab8 55%, #2491d1 100%);
        --app-bg: radial-gradient(circle at 10% 2%, rgba(46, 150, 214, 0.18), transparent 24%), linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
        --mini-card-bg: linear-gradient(180deg, rgba(35, 53, 72, 0.98), rgba(30, 45, 61, 0.96));
        --tab-list-bg: rgba(31, 47, 63, 0.92); --hero-text: #f8fbff;
    }
""" if is_dark else """
    :root {
        --bg-top: #f7f9fc; --bg-bottom: #eef3f8; --ink-900: #10233d; --ink-700: #344054; --ink-500: #667085;
        --card: #ffffff; --card-soft: #f8fafc; --line: #e2e8f0; --primary: #0d47a1; --primary-strong: #1f7ae0;
        --hero-bg: linear-gradient(135deg, #0d47a1 0%, #177ae0 100%);
        --app-bg: radial-gradient(circle at top left, rgba(34, 139, 230, 0.14), transparent 30%), linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
        --mini-card-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(247, 250, 255, 0.9));
        --tab-list-bg: rgba(255, 255, 255, 0.64); --hero-text: #ffffff;
    }
"""


st.markdown(
    "<style>\n" + css_theme + """
    .stApp { background: var(--app-bg); color: var(--ink-900); }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    .hero-shell { background: var(--hero-bg); border-radius: 28px; padding: 1.2rem 1.4rem; box-shadow: 0 18px 34px rgba(0,0,0,0.24); margin-bottom: 1rem; }
    .hero-badge { display: inline-flex; border-radius: 999px; padding: 0.3rem 0.75rem; font-weight: 700; font-size: 0.82rem; color: #eef7ff; background: rgba(255,255,255,0.16); }
    .hero-title { text-align: center; margin: 0.9rem 0 0.2rem; font-weight: 900; color: var(--hero-text); font-size: clamp(1.9rem, 3.1vw, 3rem); }
    .hero-subtitle { text-align: center; margin: 0; color: rgba(248, 251, 255, 0.82); font-size: 0.98rem; }
    .mini-card { background: var(--mini-card-bg); border: 1px solid var(--line); border-radius: 14px; padding: 0.55rem 0.7rem; box-shadow: 0 8px 18px rgba(0,0,0,0.22); min-height: 72px; }
    .mini-label { font-size: 0.7rem; text-transform: uppercase; font-weight: 800; color: var(--ink-500); margin-bottom: 0.2rem; }
    .mini-value { font-size: 1.3rem; font-weight: 900; color: var(--ink-900); }
    .mini-note { font-size: 0.76rem; color: var(--ink-700); }
    .stTabs [data-baseweb="tab-list"] { gap: 0.45rem; padding: 0.3rem; background: var(--tab-list-bg); border-radius: 999px; }
    .history-instruction { margin: 0 0 1.8rem; color: var(--ink-700); font-size: 1rem; }
    .history-label { margin: 0 0 0.25rem; color: var(--ink-700); font-size: 1rem; }
    [class*="st-key-history_period"] [data-testid="stDateInput"] { width: 250px; max-width: 100%; }
    .history-stations [data-testid="stCheckbox"] label > div:first-child { border-radius: 50%; }
    .history-generate button { width: auto; min-width: 0; padding: 0.35rem 0.75rem; }
    .alert-critical { border-radius: 14px; background: rgba(215, 38, 61, 0.16); padding: 1rem; font-weight: 600; margin-bottom: 1rem; }
    .alert-warning { border-radius: 14px; background: rgba(240, 140, 0, 0.16); padding: 1rem; font-weight: 600; margin-bottom: 1rem; }
    .alert-success { border-radius: 14px; background: rgba(43, 147, 72, 0.16); padding: 1rem; font-weight: 600; margin-bottom: 1rem; }
    div[data-testid="stPlotlyChart"] { background: var(--card-soft); border: 1px solid var(--line); border-radius: 16px; padding: 0.35rem; }
    div[data-testid="stExpander"] { background: var(--card); border: 1px solid var(--line); border-radius: 16px; }
    div[data-testid="stCustomComponentV1"] { background: transparent !important; border-radius: 16px; overflow: hidden; }
    div[data-testid="stCustomComponentV1"] iframe { display: block; background: transparent !important; border: 0; border-radius: 16px; clip-path: inset(0 round 16px); -webkit-clip-path: inset(0 round 16px); overflow: hidden; }
    p, span, label { color: var(--ink-700); }
    </style>
    """,
    unsafe_allow_html=True,
)


def _mini_card(titulo: str, valor: str, nota: str = "") -> None:
    st.markdown(
        f'<div class="mini-card">'
        f'<div class="mini-label">{titulo}</div>'
        f'<div class="mini-value">{valor}</div>'
        f'<div class="mini-note">{nota}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


st.markdown(
    f'<div class="hero-shell">'
    f'<div class="hero-badge">{t["hero_badge"]}</div>'
    f'<div class="hero-title">{t["hero_title"]}</div>'
    f'<div class="hero-subtitle">{t["hero_subtitle"]}</div>'
    f"</div>",
    unsafe_allow_html=True,
)


_, ctrl_col1, ctrl_col2 = st.columns(
    [7, 1.5, 1.5],
    vertical_alignment="center",
)

with ctrl_col1:
    idioma_ingles = (
        st.session_state.get("idioma_ativo", "Português") == "English"
    )

    if st.toggle("🌐 PT / EN", value=idioma_ingles) != idioma_ingles:
        st.session_state["idioma_ativo"] = (
            "English"
            if st.session_state["idioma_ativo"] == "Português"
            else "Português"
        )
        st.rerun()

idioma_sel = st.session_state["idioma_ativo"]
t = TRADUCOES[idioma_sel]


with ctrl_col2:
    tema_atual = st.session_state.get("is_dark_theme", True)

    if st.toggle("⛅ / ⛈️", value=tema_atual) != tema_atual:
        st.session_state["is_dark_theme"] = not tema_atual
        st.rerun()

is_dark = st.session_state.get("is_dark_theme", True)


st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)

tab_mapa, tab_hist, tab_pub = st.tabs(
    [
        t["tab_map"],
        t["tab_hist"],
        t["tab_pub"],
    ]
)


# ==========================================
# ABA 1: RISCO HOJE (TEMPO REAL - HOJE)
# ==========================================
with tab_mapa:
    fuso = pytz.timezone("America/Recife")
    agora = datetime.now(fuso)
    data_hoje_str = agora.strftime("%Y-%m-%d")

    df_am = carregar_dados_mare_cache(ARQUIVO_MARE_AM)

    # ALTERADO:
    # Carrega o arquivo incremental produzido pelo workflow:
    # chuva_recife_YYYY-MM-DD.csv
    df_chuva_raw = carregar_dados_chuva_tempo_real(data_hoje_str)

    df_final = pd.DataFrame()

    if not df_chuva_raw.empty and not df_am.empty:
        mapa_estacoes = {
            "261160614A": "Campina do Barreto",
            "261160618A": "Torreão",
            "261160623A": "RECIFE - APAC",
            "261160609A": "Imbiribeira", 
            "261160603A": "Dois Irmãos",
        }

        if "codestacao" in df_chuva_raw.columns:
            df_chuva_raw["nome"] = (
                df_chuva_raw["codestacao"]
                .astype(str)
                .str.strip()
                .map(mapa_estacoes)
            )

        datas_processar = sorted(
            df_chuva_raw["datahora"]
            .dt.strftime("%Y-%m-%d")
            .dropna()
            .unique()
        )

        df_vp = processar_dados_chuva_simplificado(
            df_chuva_raw,
            datas_processar,
            ESTACOES_DESEJADAS,
        )

        df_final = pd.merge(
            df_vp,
            df_am,
            on=["data", "hora_ref"],
            how="left",
        )

        # Mantém o valor real no diagrama.
        df_final["AM_real"] = df_final["AM"]

        # Mantém a regra de negócio:
        # maré abaixo de 1 m recebe 1 m SOMENTE para calcular risco.
        df_final["AM_calc"] = df_final["AM_real"].copy()

        df_final.loc[
            df_final["AM_calc"].notna()
            & (df_final["AM_calc"] < 1),
            "AM_calc",
        ] = 1

        df_final["Nivel_Risco_Valor"] = (
            df_final["VP"] * df_final["AM_calc"]
        ).fillna(0)

        bins = [-np.inf, 30, 50, 100, np.inf]

        df_final["Classificacao_Risco"] = pd.cut(
            df_final["Nivel_Risco_Valor"],
            bins=bins,
            labels=["Baixo", "Moderado", "Moderado Alto", "Alto"],
        )

        # IMPORTANTE:
        # Não chama mais salvar_risco_no_csv().
        # O arquivo de chuva diário é bruto e pertence ao workflow incremental.

    if df_final.empty:
        st.warning(t["aguardando_dados"])

    else:
        if (
            not st.session_state["bairro_selecionado"]
            or st.session_state["bairro_selecionado"]
            not in ESTACOES_DESEJADAS
        ):
            st.session_state["bairro_selecionado"] = ESTACOES_DESEJADAS[0]

        bairro = st.session_state["bairro_selecionado"]

        df_hoje = df_final[
            df_final["data"] == data_hoje_str
        ]

        historico_bairro = df_hoje[
            df_hoje["nome"] == bairro
        ].sort_values(by="hora_ref")

        hora_mare_atual = agora.strftime("%H:00:00")

        mare_hora_atual = df_am[
            (df_am["data"] == data_hoje_str)
            & (df_am["hora_ref"] == hora_mare_atual)
        ]

        mare_atual = (
            float(mare_hora_atual.iloc[0]["AM"])
            if not mare_hora_atual.empty
            else 0.0
        )

        risco_atual = (
            historico_bairro.iloc[-1]["Classificacao_Risco"]
            if not historico_bairro.empty
            else "Baixo"
        )

        chuva_12h = 0.0
        chuva_24h = 0.0
        usou_api_cemaden = False

        token_api = obter_token_cemaden()

        if token_api:
            df_acumulados_api = carregar_acumulados_api_cemaden(
                token_api
            )

            if (
                not df_acumulados_api.empty
                and "codestacao" in df_acumulados_api.columns
            ):
                df_acumulados_api["nome"] = (
                    df_acumulados_api["codestacao"]
                    .astype(str)
                    .str.strip()
                    .map(mapa_estacoes)
                )

                ac_bairro = df_acumulados_api[
                    df_acumulados_api["nome"] == bairro
                ]

                if not ac_bairro.empty:
                    chuva_12h = float(
                        ac_bairro["acc12hr"].iloc[0]
                    )
                    chuva_24h = float(
                        ac_bairro["acc24hr"].iloc[0]
                    )
                    usou_api_cemaden = True

        if not usou_api_cemaden:
            df_raw_bairro = df_chuva_raw[
                df_chuva_raw["nome"] == bairro
            ].copy()

            agora_naive = agora.replace(tzinfo=None)

            if "valor" in df_raw_bairro.columns:
                chuva_24h = float(
                    df_raw_bairro[
                        df_raw_bairro["datahora"]
                        >= agora_naive - timedelta(hours=24)
                    ]["valor"].sum()
                )

                chuva_12h = float(
                    df_raw_bairro[
                        df_raw_bairro["datahora"]
                        >= agora_naive - timedelta(hours=12)
                    ]["valor"].sum()
                )

        legenda_card = (
            "acumulado API CEMADEN"
            if usou_api_cemaden
            else "acumulado local"
        )

        coord_atual = COORDENADAS_ESTACOES.get(
            bairro,
            [-8.05, -34.90],
        )

        df_noaa = buscar_previsao_noaa_openmeteo(
            lat=coord_atual[0],
            lon=coord_atual[1],
        )

        html_prev_itens = ""
        temp_atual_str = "--°C"

        condicao_atual_str = (
            "Carregando..."
            if idioma_sel == "Português"
            else "Loading..."
        )

        icone_atual_str = "☀️"

        if not df_noaa.empty:
            agora_utc = pd.Timestamp.now(tz="America/Recife")

            idx_atual = (
                df_noaa["date"] - agora_utc
            ).abs().idxmin()

            temp_atual_str = (
                f'{df_noaa.loc[idx_atual, "temperature_2m"]:.0f}°C'
            )

            icone_atual_str, condicao_atual_str = (
                interpretar_codigo_clima(
                    df_noaa.loc[idx_atual, "weather_code"],
                    df_noaa.loc[
                        idx_atual,
                        "precipitation_probability",
                    ],
                    df_noaa.loc[idx_atual, "precipitation"],
                    df_noaa.loc[idx_atual, "date"].hour,
                    idioma_sel,
                )
            )

            for i in range(
                idx_atual,
                min(idx_atual + 24, len(df_noaa)),
            ):
                row = df_noaa.iloc[i]

                ico_item, _ = interpretar_codigo_clima(
                    row["weather_code"],
                    row["precipitation_probability"],
                    row["precipitation"],
                    row["date"].hour,
                    idioma_sel,
                )

                html_prev_itens += (
                    '<div style="text-align: center; min-width: 60px; '
                    'padding: 0 4px; display: inline-block;">'
                    '<div style="font-size: 0.72rem; color: var(--ink-500); '
                    'font-weight: 800; margin-bottom: 2px;">'
                    f'{row["date"].strftime("%H:00")}'
                    "</div>"
                    '<div style="font-size: 1.15rem; margin: 1px 0;">'
                    f"{ico_item}"
                    "</div>"
                    '<div style="font-size: 0.78rem; color: var(--ink-900); '
                    'font-weight: 900;">'
                    f'{row["temperature_2m"]:.0f}°C'
                    "</div>"
                    '<div style="font-size: 0.68rem; color: #2e96d6; '
                    'font-weight: 700; margin-top: 2px;">'
                    f'🌧️ {int(row["precipitation_probability"])}%'
                    "</div>"
                    '<div style="font-size: 0.62rem; color: var(--ink-500); '
                    'font-weight: 600;">'
                    f'💧 {row["precipitation"]:.1f} mm'
                    "</div>"
                    "</div>"
                )

        titulo_card_noaa = (
            f"{bairro} • Previsão NOAA"
            if idioma_sel == "Português"
            else f"{bairro} • NOAA Forecast"
        )

        col_widget, col_cards = st.columns(
            [1.6, 2.4],
            gap="medium",
            vertical_alignment="center",
        )

        with col_widget:
            st.markdown(
                f'<div class="mini-card" '
                f'style="padding: 0.6rem 0.9rem; display: flex; '
                f'flex-direction: column; justify-content: space-between; '
                f'min-height: 125px;">'
                f'<div style="display: flex; justify-content: space-between; '
                f'align-items: center;">'
                f'<div>'
                f'<div class="mini-label">{titulo_card_noaa}</div>'
                f'<div style="display: flex; align-items: baseline; '
                f'gap: 8px; margin-top: 1px;">'
                f'<span style="font-size: 1.45rem; font-weight: 900; '
                f'color: var(--ink-900);">{temp_atual_str}</span>'
                f'<span style="font-size: 0.8rem; font-weight: 700; '
                f'color: var(--ink-700);">{condicao_atual_str}</span>'
                f"</div>"
                f"</div>"
                f'<div style="font-size: 2.1rem; line-height: 1;">'
                f"{icone_atual_str}"
                f"</div>"
                f"</div>"
                f'<div style="display: flex; justify-content: flex-start; '
                f'align-items: center; border-top: 1px solid var(--line); '
                f'padding-top: 6px; margin-top: 4px; overflow-x: auto; '
                f'gap: 8px; scrollbar-width: thin;">'
                f"{html_prev_itens}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            st.caption(
                "Fonte: Modelo NOAA GFS (Open-Meteo). "
                "*Por se tratar de uma projeção numérica, podem ocorrer "
                "variações locais.*"
                if idioma_sel == "Português"
                else "Source: NOAA GFS Model (Open-Meteo). "
                "*As a numerical projection, local variations may occur.*"
            )

        with col_cards:
            topo2, topo3, topo4, topo5 = st.columns(
                4,
                vertical_alignment="center",
            )

            with topo2:
                st.selectbox(
                    t["selecionar_estacao"],
                    options=ESTACOES_DESEJADAS,
                    key="bairro_selecionado",
                )

            with topo3:
                _mini_card(
                    t["chuva_24h"],
                    f"{chuva_24h:.1f} mm",
                    legenda_card,
                )

            with topo4:
                _mini_card(
                    t["chuva_12h"],
                    f"{chuva_12h:.1f} mm",
                    legenda_card,
                )

            with topo5:
                _mini_card(
                    t["mare_atual"],
                    f"{mare_atual:.2f} m",
                    t["t_astronomica"],
                )

        st.markdown(
            "<hr style='margin: 0.55rem 0 1rem; border: 0; "
            "border-top: 1px solid var(--line);'>",
            unsafe_allow_html=True,
        )

        analise_col, mapa_col = st.columns(
            [1.5, 1],
            gap="large",
        )

        with analise_col:
            st.markdown(
                f"<h4>{t['titulo_umidade']}</h4>",
                unsafe_allow_html=True,
            )

            dados_meteo = buscar_umidade_openmeteo(
                coord_atual[0],
                coord_atual[1],
            )

            sup, trans, inter, prof = extrair_umidade_hora_atual(
                dados_meteo,
                agora,
            )

            u1, u2, u3, u4 = st.columns(4)

            with u1:
                _mini_card(
                    t["camada_sup"],
                    f"{sup:.3f} m³/m³",
                    t["desc_sup"],
                )

            with u2:
                _mini_card(
                    t["camada_trans"],
                    f"{trans:.3f} m³/m³",
                    t["desc_trans"],
                )

            with u3:
                _mini_card(
                    t["camada_int"],
                    f"{inter:.3f} m³/m³",
                    t["desc_int"],
                )

            with u4:
                _mini_card(
                    t["camada_prof"],
                    f"{prof:.3f} m³/m³",
                    t["desc_prof"],
                )

            st.markdown(
                f"<h4>{t['titulo_diagrama']}</h4>",
                unsafe_allow_html=True,
            )

            if not historico_bairro.empty:
                fig = go.Figure()

                lim_x = max(
                    110,
                    historico_bairro["VP"].max() * 1.2,
                )

                x_grid = np.arange(0, lim_x, 1)
                y_grid = np.linspace(0, 5, 100)

                z_grid = np.array(
                    [x * y for y in y_grid for x in x_grid]
                ).reshape(len(y_grid), len(x_grid))

                fig.add_trace(
                    go.Heatmap(
                        x=x_grid,
                        y=y_grid,
                        z=z_grid,
                        colorscale=[
                            [0, "#90EE90"],
                            [0.3, "#FFD700"],
                            [0.5, "#FFA500"],
                            [1.0, "#D32F2F"],
                        ],
                        showscale=False,
                        zmin=0,
                        zmax=100,
                        hoverinfo="none",
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=historico_bairro["VP"],
                        y=historico_bairro["AM_real"],
                        mode="lines",
                        line=dict(
                            color="black",
                            width=1,
                            dash="dash",
                        ),
                        hoverinfo="none",
                        showlegend=False,
                    )
                )

                mapa_de_cores = {
                    "Alto": "#D32F2F",
                    "Moderado Alto": "#FFA500",
                    "Moderado": "#FFC107",
                    "Baixo": "#4CAF50",
                }

                total_pontos = len(historico_bairro)

                for idx, (_, ponto) in enumerate(
                    historico_bairro.iterrows()
                ):
                    cor_ponto = mapa_de_cores.get(
                        ponto["Classificacao_Risco"],
                        "black",
                    )

                    risco_ui_str = RISCO_UI[idioma_sel].get(
                        ponto["Classificacao_Risco"],
                        ponto["Classificacao_Risco"],
                    )

                    is_ultimo = idx == total_pontos - 1
                    is_penultimo = idx == total_pontos - 2

                    if is_ultimo:
                        fig.add_trace(
                            go.Scatter(
                                x=[ponto["VP"]],
                                y=[ponto["AM_real"]],
                                mode="markers",
                                marker=dict(
                                    color="rgba(0,0,0,0)",
                                    size=22,
                                    line=dict(
                                        width=2.5,
                                        color=(
                                            "white"
                                            if is_dark
                                            else "#10233d"
                                        ),
                                    ),
                                ),
                                hoverinfo="none",
                                showlegend=False,
                            )
                        )

                        tamanho_bolinha = 14
                        opacidade_ponto = 1.0
                        largura_borda = 2
                        cor_borda = (
                            "white"
                            if is_dark
                            else "black"
                        )

                    elif is_penultimo:
                        tamanho_bolinha = 11
                        opacidade_ponto = 0.85
                        largura_borda = 1.5
                        cor_borda = "black"

                    else:
                        tamanho_bolinha = 7
                        opacidade_ponto = 0.4
                        largura_borda = 1
                        cor_borda = "black"

                    fig.add_trace(
                        go.Scatter(
                            x=[ponto["VP"]],
                            y=[ponto["AM_real"]],
                            mode="markers",
                            marker=dict(
                                color=cor_ponto,
                                size=tamanho_bolinha,
                                opacity=opacidade_ponto,
                                line=dict(
                                    width=largura_borda,
                                    color=cor_borda,
                                ),
                            ),
                            hoverinfo="text",
                            hovertext=(
                                f"<b>{t['hora']}:</b> "
                                f"{ponto['hora_ref']}"
                                f"<br><b>{t['risco']}:</b> "
                                f"{risco_ui_str}"
                                f"<br><b>VP:</b> "
                                f"{ponto['VP']:.2f}"
                                f"<br><b>AM:</b> "
                                f"{ponto['AM_real']:.2f}"
                            ),
                            showlegend=False,
                        )
                    )

                if total_pontos >= 2:
                    fig.add_annotation(
                        x=historico_bairro.iloc[-1]["VP"],
                        y=historico_bairro.iloc[-1]["AM_real"],
                        ax=historico_bairro.iloc[-2]["VP"],
                        ay=historico_bairro.iloc[-2]["AM_real"],
                        xref="x",
                        yref="y",
                        axref="x",
                        ayref="y",
                        showarrow=True,
                        arrowhead=2,
                        arrowsize=1.2,
                        arrowwidth=2,
                        standoff=8,
                        arrowcolor=(
                            "#2e96d6"
                            if is_dark
                            else "#1f7ae0"
                        ),
                    )

                fig.update_layout(
                    xaxis_title=t["eixo_x"],
                    yaxis_title=t["eixo_y"],
                    margin=dict(l=40, r=40, t=40, b=40),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(
                        color=(
                            "#e2e8f0"
                            if is_dark
                            else "#344054"
                        )
                    ),
                    xaxis=dict(
                        gridcolor=(
                            "#3b556d"
                            if is_dark
                            else "rgba(148,163,184,0.18)"
                        ),
                        zeroline=False,
                    ),
                    yaxis=dict(
                        gridcolor=(
                            "#3b556d"
                            if is_dark
                            else "rgba(148,163,184,0.18)"
                        ),
                        zeroline=False,
                    ),
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"chart_risco_hoje_{bairro}_{data_hoje_str}",
                )

            else:
                st.info(t["sem_dados_diagrama"])

        with mapa_col:
            st.markdown(
                "<div style='height: 60px;'></div>",
                unsafe_allow_html=True,
            )

            if risco_atual == "Alto":
                st.markdown(
                    (
                        f"<div class='alert-critical'>"
                        f"{t['alerta_critico'].format(bairro)}"
                        f"</div>"
                    ),
                    unsafe_allow_html=True,
                )

            elif risco_atual in ["Moderado Alto", "Moderado"]:
                st.markdown(
                    (
                        f"<div class='alert-warning'>"
                        f"{t['alerta_atencao'].format(bairro)}"
                        f"</div>"
                    ),
                    unsafe_allow_html=True,
                )

            else:
                st.markdown(
                    (
                        f"<div class='alert-success'>"
                        f"{t['alerta_normal'].format(bairro)}"
                        f"</div>"
                    ),
                    unsafe_allow_html=True,
                )

            st.markdown(
                "<div style='height: 70px;'></div>",
                unsafe_allow_html=True,
            )

            m = folium.Map(
                location=[-8.05, -34.90],
                zoom_start=12,
                tiles="OpenStreetMap",
            )

            m.get_root().header.add_child(
                folium.Element(
                    """
                    <style>
                        html, body {
                            margin: 0;
                            background: transparent !important;
                        }

                        .leaflet-container {
                            border-radius: 16px !important;
                            overflow: hidden !important;
                        }
                    </style>
                    """
                )
            )

            riscos_atuais = (
                df_hoje.groupby("nome")
                .last()["Classificacao_Risco"]
                .to_dict()
            )

            for est_nome, coords in COORDENADAS_ESTACOES.items():
                r_est = riscos_atuais.get(est_nome, "Baixo")

                icon_color = (
                    "red"
                    if r_est == "Alto"
                    else (
                        "orange"
                        if r_est in ["Moderado Alto", "Moderado"]
                        else "green"
                    )
                )

                folium.Marker(
                    location=coords,
                    icon=folium.Icon(
                        color=icon_color,
                        icon=(
                            "info-sign"
                            if est_nome == bairro
                            else "map-marker"
                        ),
                    ),
                    popup=folium.Popup(
                        (
                            f"<b>{est_nome}</b><br>"
                            f"{t['popup_risco']}: "
                            f"{RISCO_UI[idioma_sel].get(r_est, r_est)}"
                        ),
                        max_width=250,
                    ),
                    tooltip=est_nome,
                ).add_to(m)

            mapa_interativo = st_folium(
                m,
                height=450,
                width="100%",
                returned_objects=["last_object_clicked"],
            )

            if (
                mapa_interativo
                and mapa_interativo.get("last_object_clicked")
            ):
                est_clicada = min(
                    COORDENADAS_ESTACOES.keys(),
                    key=lambda k: (
                        COORDENADAS_ESTACOES[k][0]
                        - mapa_interativo["last_object_clicked"]["lat"]
                    ) ** 2
                    + (
                        COORDENADAS_ESTACOES[k][1]
                        - mapa_interativo["last_object_clicked"]["lng"]
                    ) ** 2,
                )

                if est_clicada != st.session_state.get(
                    "bairro_selecionado"
                ):
                    st.session_state["bairro_selecionado"] = est_clicada
                    st.rerun()


# ==========================================
# ABA 2: DADOS HISTÓRICOS (INTERVALO LIVRE ATÉ ONTEM)
# ==========================================
with tab_hist:
    df_hist_geral = carregar_historico_consolidado()

    if df_hist_geral.empty:
        st.warning(
            "O arquivo `historico_risco-final.csv` não foi encontrado "
            "ou está vazio na raiz do projeto."
        )

    else:
        data_hoje_dt = pd.to_datetime(data_hoje_str).date()
        max_data_permitida = data_hoje_dt - timedelta(days=1)

        df_passado = df_hist_geral[
            pd.to_datetime(df_hist_geral["data"]).dt.date
            <= max_data_permitida
        ]

        if df_passado.empty:
            st.info(
                "Ainda não há dados históricos disponíveis no arquivo."
            )

        else:
            min_data_disp = pd.to_datetime(
                df_passado["data"]
            ).min().date()

            max_data_disp = pd.to_datetime(
                df_passado["data"]
            ).max().date()

            default_inicio = min_data_disp

            limite_fim_hist = min(
                max_data_permitida,
                max_data_disp,
            )

            st.markdown(
                (
                    "<p class='history-instruction'>"
                    "Selecione o período desejado, escolha as estações "
                    "e clique em Gerar para visualizar os diagramas "
                    "históricos."
                    "</p>"
                ),
                unsafe_allow_html=True,
            )

            col_sel1, col_sel2 = st.columns(
                [0.62, 0.9],
                gap="small",
                vertical_alignment="top",
            )

            with col_sel1:
                with st.container(key="history_period"):
                    st.markdown(
                        "<p class='history-label'>Período</p>",
                        unsafe_allow_html=True,
                    )

                    intervalo_datas = st.date_input(
                        (
                            "Período"
                            if idioma_sel == "Português"
                            else "Date range"
                        ),
                        value=(default_inicio, limite_fim_hist),
                        min_value=min_data_disp,
                        max_value=limite_fim_hist,
                        format="YYYY-MM-DD",
                        label_visibility="collapsed",
                        key="historico_intervalo_datas",
                    )

            with col_sel2:
                st.markdown(
                    "<p class='history-label'>Estações</p>",
                    unsafe_allow_html=True,
                )

                station_cols = st.columns(2, gap="small")
                station_checks = {}

                for index, estacao in enumerate(
                    ESTACOES_DESEJADAS
                ):
                    with station_cols[index % 2]:
                        station_checks[estacao] = st.checkbox(
                            estacao,
                            value=(
                                estacao == ESTACOES_DESEJADAS[0]
                            ),
                            key=f"historico_estacao_{estacao}",
                        )

                estacoes_escolhidas = [
                    estacao
                    for estacao, selecionada
                    in station_checks.items()
                    if selecionada
                ]

                with station_cols[1]:
                    btn_carregar = st.button(
                        (
                            "Gerar"
                            if idioma_sel == "Português"
                            else "Generate"
                        ),
                        type="primary",
                    )

            st.markdown(
                "<div style='height: 0.5rem;'></div>---",
                unsafe_allow_html=True,
            )

            if btn_carregar:
                if isinstance(intervalo_datas, tuple):
                    if len(intervalo_datas) == 2:
                        data_ini, data_fim = intervalo_datas
                    elif len(intervalo_datas) == 1:
                        data_ini = intervalo_datas[0]
                        data_fim = intervalo_datas[0]
                    else:
                        data_ini = default_inicio
                        data_fim = default_inicio
                else:
                    data_ini = intervalo_datas
                    data_fim = intervalo_datas

                if data_ini > data_fim:
                    st.warning(
                        "A data inicial deve ser anterior ou igual "
                        "à data final."
                    )
                    st.stop()

                data_ini_str = data_ini.strftime("%Y-%m-%d")
                data_fim_str = data_fim.strftime("%Y-%m-%d")

                if not estacoes_escolhidas:
                    st.warning(
                        "Por favor, selecione ao menos uma estação."
                    )

                else:
                    with st.spinner(
                        (
                            "Carregando e processando histórico..."
                            if idioma_sel == "Português"
                            else "Loading and processing history..."
                        )
                    ):
                        df_filtrado = df_passado[
                            (
                                df_passado["data"]
                                >= data_ini_str
                            )
                            & (
                                df_passado["data"]
                                <= data_fim_str
                            )
                            & (
                                df_passado["nomeEstacao"].isin(
                                    estacoes_escolhidas
                                )
                            )
                        ].sort_values(by=["data", "hora_ref"])

                    if df_filtrado.empty:
                        st.info(
                            "Nenhum registro encontrado para a "
                            "combinação de datas e estações selecionadas."
                        )

                    else:
                        mapa_de_cores = {
                            "Alto": "#D32F2F",
                            "Moderado Alto": "#FFA500",
                            "Moderado": "#FFC107",
                            "Baixo": "#4CAF50",
                        }

                        datas_presentes = sorted(
                            df_filtrado["data"].unique()
                        )

                        for estacao in estacoes_escolhidas:
                            for dt in datas_presentes:
                                df_sub = df_filtrado[
                                    (
                                        df_filtrado["nomeEstacao"]
                                        == estacao
                                    )
                                    & (df_filtrado["data"] == dt)
                                ]

                                if df_sub.empty:
                                    continue

                                st.markdown(
                                    (
                                        "<h4 style='margin-top: 1.5rem; "
                                        "color: var(--ink-900);'>"
                                        f"📍 {estacao} — 📅 {dt}"
                                        "</h4>"
                                    ),
                                    unsafe_allow_html=True,
                                )

                                fig_hist = go.Figure()

                                lim_x = max(
                                    110,
                                    df_sub["VP"].max() * 1.2,
                                )

                                x_grid = np.arange(0, lim_x, 1)
                                y_grid = np.linspace(0, 5, 100)

                                z_grid = np.array(
                                    [
                                        x * y
                                        for y in y_grid
                                        for x in x_grid
                                    ]
                                ).reshape(
                                    len(y_grid),
                                    len(x_grid),
                                )

                                fig_hist.add_trace(
                                    go.Heatmap(
                                        x=x_grid,
                                        y=y_grid,
                                        z=z_grid,
                                        colorscale=[
                                            [0, "#90EE90"],
                                            [0.3, "#FFD700"],
                                            [0.5, "#FFA500"],
                                            [1.0, "#D32F2F"],
                                        ],
                                        showscale=False,
                                        zmin=0,
                                        zmax=100,
                                        hoverinfo="none",
                                    )
                                )

                                fig_hist.add_trace(
                                    go.Scatter(
                                        x=df_sub["VP"],
                                        y=df_sub["AM"],
                                        mode="lines",
                                        line=dict(
                                            color="black",
                                            width=1.5,
                                            dash="dash",
                                        ),
                                        hoverinfo="none",
                                        showlegend=False,
                                    )
                                )

                                fig_hist.add_trace(
                                    go.Scatter(
                                        x=df_sub["VP"],
                                        y=df_sub["AM"],
                                        mode="markers",
                                        marker=dict(
                                            color=[
                                                mapa_de_cores.get(
                                                    r,
                                                    "black",
                                                )
                                                for r in df_sub[
                                                    "Classificacao_Risco"
                                                ]
                                            ],
                                            size=10,
                                            line=dict(
                                                width=1,
                                                color="black",
                                            ),
                                        ),
                                        hoverinfo="text",
                                        hovertext=[
                                            (
                                                "<b>Hora:</b> "
                                                f"{r['hora_ref']}"
                                                "<br><b>Risco:</b> "
                                                f"{r['Classificacao_Risco']}"
                                                "<br><b>VP:</b> "
                                                f"{r['VP']:.2f}"
                                                "<br><b>AM:</b> "
                                                f"{r['AM']:.2f}"
                                            )
                                            for _, r in df_sub.iterrows()
                                        ],
                                        showlegend=False,
                                    )
                                )

                                fig_hist.update_layout(
                                    xaxis_title=t["eixo_x"],
                                    yaxis_title=t["eixo_y"],
                                    margin=dict(
                                        l=40,
                                        r=40,
                                        t=40,
                                        b=40,
                                    ),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    font=dict(
                                        color=(
                                            "#e2e8f0"
                                            if is_dark
                                            else "#344054"
                                        )
                                    ),
                                    xaxis=dict(
                                        gridcolor=(
                                            "#3b556d"
                                            if is_dark
                                            else "rgba(148,163,184,0.18)"
                                        ),
                                        zeroline=False,
                                    ),
                                    yaxis=dict(
                                        gridcolor=(
                                            "#3b556d"
                                            if is_dark
                                            else "rgba(148,163,184,0.18)"
                                        ),
                                        zeroline=False,
                                    ),
                                )

                                st.plotly_chart(
                                    fig_hist,
                                    use_container_width=True,
                                    key=f"chart_hist_{estacao}_{dt}",
                                )


# ==========================================
# ABA 3: METODOLOGIA
# ==========================================
with tab_pub:
    if idioma_sel == "Português":
        st.markdown("**Embasamento metodológico:**")

        st.markdown(
            "[**Risco de Inundação e Alagamento: "
            "Uma Abordagem de Visualização Geométrica**]"
            "(https://arandu.ufrpe.br/items/"
            "02fcdf72-754d-4615-bcbe-72b152c515c9)"
        )

        st.markdown(
            "🔹 *Estudo focado na modelagem geométrica e espacial "
            "para análise e mapeamento de risco de inundação e "
            "alagamento.*"
        )

        st.markdown("Autor: Igor Gomes")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            "[**Painel Interativo de Monitoramento de Risco de "
            "Alagamentos para a Cidade do Recife**]"
            "(https://arandu.ufrpe.br/items/"
            "08489bec-0f03-4071-a0ef-563ae8ea54b8)"
        )

        st.markdown(
            "🔹 *Desenvolvimento de plataforma web que integra dados "
            "meteorológicos e maregráficos em tempo real para suporte "
            "a decisões.*"
        )

        st.markdown("Autor: Rafaella Moura")

    else:
        st.markdown("**Methodological foundation:**")

        st.markdown(
            "[**Flood and Inundation Risk: "
            "A Geometric Visualization Approach**]"
            "(https://arandu.ufrpe.br/items/"
            "02fcdf72-754d-4615-bcbe-72b152c515c9)"
        )

        st.markdown(
            "🔹 *Research focused on geometric and spatial modeling "
            "for mapping flood and inundation risk areas.*"
        )

        st.markdown("Autor: Igor Gomes")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            "[**Interactive Flood Risk Monitoring Dashboard for "
            "the City of Recife**]"
            "(https://arandu.ufrpe.br/items/"
            "08489bec-0f03-4071-a0ef-563ae8ea54b8)"
        )

        st.markdown(
            "🔹 *Development of an analytical web platform integrating "
            "meteorological and tidal data in real-time for decision "
            "support.*"
        )

        st.markdown("Autor: Rafaella Moura")


# ==========================================
# RODAPÉ
# ==========================================
st.markdown("---")


def get_image_base64(path_str):
    img_path = Path(path_str)

    if img_path.exists():
        with open(img_path, "rb") as arquivo:
            return (
                "data:image/png;base64,"
                f"{base64.b64encode(arquivo.read()).decode()}"
            )

    return ""


logos = [
    get_image_base64(BASE_DIR / f"logos/{logo}.png")
    for logo in [
        "ilika",
        "irrd",
        "ipecti",
        "ufpe",
        "ufrpe",
        "geosere",
    ]
]

titulo_parceiros = (
    "Instituições e Parceiros:"
    if idioma_sel == "Português"
    else "Institutions and Partners:"
)

st.markdown(
    f'<div style="background-color: #ffffff; padding: 24px; '
    f'border-radius: 12px; margin-top: 40px; '
    f'box-shadow: 0 4px 6px rgba(0,0,0,0.05);">'
    f'<p style="color: #1a1a1a; font-weight: 700; text-align: center; '
    f'margin-bottom: 20px; font-size: 1.1rem;">'
    f"{titulo_parceiros}"
    f"</p>"
    f'<div style="display: flex; justify-content: center; '
    f'align-items: center; flex-wrap: wrap; gap: 40px;">'
    + "".join(
        [
            (
                f'<img src="{logo_base64}" '
                f'style="height: 45px; width: auto; '
                f'object-fit: contain;">'
            )
            for logo_base64 in logos
            if logo_base64
        ]
    )
    + "</div></div>",
    unsafe_allow_html=True,
)