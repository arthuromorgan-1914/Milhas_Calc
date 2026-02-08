import streamlit as st
import pandas as pd
import requests
import sqlite3
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List

# --- CONFIGURAÇÃO DA PÁGINA (MOBILE FIRST) ---
st.set_page_config(
    page_title="MilhasApp",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed" # Começa fechado no mobile
)

# --- TRUQUE DE CSS PARA PARECER APP NATIVO ---
st.markdown("""
    <style>
        /* Remove espaços em branco excessivos no topo */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        /* Esconde o menu padrão e rodapé */
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Botões maiores para clicar com o dedo */
        .stButton button {
            width: 100%;
            border-radius: 12px;
            height: 3em;
            font-weight: bold;
        }
        
        /* Caixas de Métricas com fundo destacado */
        div[data-testid="stMetric"] {
            background-color: #f0f2f6;
            padding: 10px;
            border-radius: 10px;
            text-align: center;
        }
    </style>
""", unsafe_allow_html=True)

# --- 1. MÓDULO DE IA (GEMINI 2.5 FLASH) ---
class AIAnalyst:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except Exception as e:
                st.error(f"Erro IA: {e}")

    def analisar_cenario(self, cenario_dict, dados_mercado):
        if not self.api_key:
            return "⚠️ Configure a API Key."
        
        prompt = f"""
        Analise esta operação de milhas aéreas para um investidor iniciante:
        OPERAÇÃO: Compra de {cenario_dict['pontos']} pontos no programa {cenario_dict['programa']}.
        INVESTIMENTO: R$ {cenario_dict['investimento']:.2f} (CPM: R$ {cenario_dict['cpm']:.2f}).
        VENDA ESPERADA: R$ {cenario_dict['preco_venda']:.2f} (Lucro: R$ {cenario_dict['lucro']:.2f}, ROI: {cenario_dict['roi']:.1f}%).
        MERCADO: O preço médio de venda hoje é R$ {dados_mercado.get(cenario_dict['programa'], 0):.2f}.
        
        Responda em 3 tópicos curtos (Markdown). Use emojis.
        Diga se o preço de venda é realista e se o risco vale a pena.
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except:
            return "Erro ao conectar com a IA."

# --- 2. GERENCIAMENTO DE BANCO DE DADOS ---
class PortfolioManager:
    def __init__(self, db_name="milhas_portfolio.db"):
        self.db_name = db_name
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_registro TEXT,
                programa TEXT,
                investimento REAL,
                pontos INTEGER,
                preco_venda REAL,
                lucro_projetado REAL,
                roi_percentual REAL
            )
        ''')
        conn.commit()
        conn.close()

    def salvar_operacao(self, dados: Dict):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operacoes (data_registro, programa, investimento, pontos, preco_venda, lucro_projetado, roi_percentual)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime("%Y-%m-%d"), dados['programa'], dados['investimento'], dados['pontos'], dados['preco_venda'], dados['lucro'], dados['roi']))
        conn.commit()
        conn.close()

    def listar_carteira(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_name)
        try:
            df = pd.read_sql_query("SELECT * FROM operacoes ORDER BY id DESC", conn)
        except: df = pd.DataFrame()
        conn.close()
        return df
    
    def excluir_operacao(self, id_op):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM operacoes WHERE id = ?", (id_op,))
        conn.commit()
        conn.close()

# --- 3. MONITOR DE OPORTUNIDADES (NOVO) ---
@st.cache_data(ttl=1800) # Cache de 30 min
def buscar_oportunidades():
    """Busca as últimas notícias de milhas e filtra promoções relevantes."""
    url = "https://www.melhorescartoes.com.br/category/programas-de-fidelidade"
    headers = {"User-Agent": "Mozilla/5.0"}
    oportunidades = []
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procura manchetes (h2 ou h3 dependendo do site)
        artigos = soup.find_all('h3') # Ajuste conforme estrutura do site alvo
        
        for artigo in artigos[:8]: # Pega as 8 primeiras
            titulo = artigo.get_text().strip()
            link = artigo.find('a')['href'] if artigo.find('a') else "#"
            
            # Filtro de Palavras-Chave (Só o que dá dinheiro)
            keywords = ["bônus", "100%", "compra de pontos", "transferência", "livelo", "esfera"]
            if any(k in titulo.lower() for k in keywords):
                oportunidades.append({"titulo": titulo, "link": link})
                
    except:
        pass
        
    return oportunidades

# --- 4. COTAÇÕES SIMPLES ---
@st.cache_data(ttl=3600)
def obter_cotacoes():
    # Simulação para performance - em produção use o scraper completo
    return {"Smiles": 17.60, "LatamPass": 23.10, "TudoAzul": 19.80}

# --- 5. INTERFACE PRINCIPAL ---
def main():
    db = PortfolioManager()
    cotacoes = obter_cotacoes()
    
    # Configuração de API Key via Secrets ou Sidebar
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    analista = AIAnalyst(api_key)

    # --- TÍTULO E MONITOR DE ALERTAS (Topo da Tela) ---
    st.title("✈️ MilhasApp")
    
    # Radar de Promoções (Aparece primeiro no Mobile)
    with st.expander("🔥 Radar de Promoções (Ao Vivo)", expanded=True):
        news = buscar_oportunidades()
        if news:
            for item in news:
                st.markdown(f"👉 **[{item['titulo']}]({item['link']})**")
        else:
            st.info("Nenhuma mega promoção detectada agora.")

    # --- ÁREA DE SIMULAÇÃO (Colapsável) ---
    # Usamos st.container para agrupar
    with st.container():
        st.write("---")
        st.subheader("Simulador Rápido")
        
        col_prog, col_bonus = st.columns(2)
        programa = col_prog.selectbox("Programa", ["Smiles", "LatamPass", "TudoAzul"])
        bonus = col_bonus.selectbox("Bônus Transf.", [100, 90, 80, 70, 60, 50, 0])
        
        col_inv, col_pontos = st.columns(2)
        investimento = col_inv.number_input("Investimento (R$)", value=3500.0, step=50.0)
        pontos_compra = col_pontos.number_input("Pontos Base", value=100000, step=1000)
        
        # Preço de Venda Inteligente (Sugere o mercado)
        preco_mercado = cotacoes.get(programa, 20.00)
        preco_venda = st.slider("Preço de Venda (R$)", 15.0, 30.0, preco_mercado, step=0.10)
        
        # Cálculos
        total_milhas = pontos_compra * (1 + (bonus / 100))
        lucro = ((total_milhas/1000) * preco_venda) - investimento
        roi = (lucro / investimento) * 100
        cpm = investimento / (total_milhas / 1000)

        # Dados para IA e Banco
        cenario = {
            "programa": programa, "investimento": investimento, "pontos": total_milhas,
            "cpm": cpm, "preco_venda": preco_venda, "lucro": lucro, "roi": roi
        }

        # --- RESULTADOS EM DESTAQUE ---
        st.markdown("### 📊 Resultado")
        
        # Layout 2x2 para mobile
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta=f"{roi:.1f}%")
        kpi2.metric("Custo Milheiro", f"R$ {cpm:.2f}", delta_color="inverse")
        
        # --- BOTÕES DE AÇÃO ---
        col_btn_ia, col_btn_save = st.columns(2)
        
        if col_btn_ia.button("✨ IA Analisar"):
            with st.spinner("Consultando..."):
                parecer = analista.analisar_cenario(cenario, cotacoes)
                st.markdown(f"""
                <div style="background-color:#F0F2F6;color:#000;padding:10px;border-radius:10px;border-left:5px solid #00C853;margin-top:10px;">
                {parecer}
                </div>
                """, unsafe_allow_html=True)
                
        if col_btn_save.button("💾 Salvar"):
            db.salvar_operacao(cenario)
            st.toast("Salvo na Carteira!", icon="✅")

    # --- CARTEIRA (No final) ---
    with st.expander("📂 Minha Carteira"):
        df = db.listar_carteira()
        if not df.empty:
            st.dataframe(df[["programa", "lucro_projetado", "roi_percentual"]], hide_index=True, use_container_width=True)
            if st.button("Limpar Último"):
                last_id = df.iloc[0]['id']
                db.excluir_operacao(int(last_id))
                st.rerun()
        else:
            st.write("Vazio.")

if __name__ == "__main__":
    main()