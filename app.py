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
    initial_sidebar_state="collapsed"
)

# --- CSS CORRIGIDO (VISUAL MOBILE & CORES) ---
st.markdown("""
    <style>
        /* 1. Ajuste de Margens para Mobile (Tela Cheia) */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 5rem; /* Espaço extra embaixo para rolagem */
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        
        /* 2. Esconde elementos desnecessários */
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* 3. Botões Grandes (Fáceis de clicar) */
        .stButton button {
            width: 100%;
            border-radius: 12px;
            height: 3.5em;
            font-weight: bold;
            border: none;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .stButton button:active {
            transform: scale(0.98);
        }
        
        /* 4. CORREÇÃO DAS CAIXAS DE RESULTADO (MÉTRICAS) */
        /* Força o fundo claro e bordas arredondadas */
        div[data-testid="stMetric"] {
            background-color: #F8F9FA !important; /* Cinza bem claro */
            border: 1px solid #E9ECEF;
            padding: 15px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        
        /* Força a cor do TÍTULO da métrica para CINZA ESCURO */
        div[data-testid="stMetric"] label {
            color: #495057 !important; 
            font-size: 0.9rem !important;
        }
        
        /* Força a cor do NÚMERO da métrica para PRETO */
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #212529 !important;
            font-weight: 700 !important;
        }
        
        /* Cor da seta de variação (Delta) */
        div[data-testid="stMetricDelta"] {
            background-color: rgba(255,255,255,0.5);
            border-radius: 5px;
            padding: 2px 5px;
            font-weight: bold;
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
            return "⚠️ Configure a API Key nos 'Secrets' do Streamlit."
        
        prompt = f"""
        Você é um consultor financeiro direto e objetivo.
        Analise esta operação de milhas aéreas:
        
        OPERAÇÃO: Compra de {cenario_dict['pontos']} pontos no programa {cenario_dict['programa']}.
        INVESTIMENTO: R$ {cenario_dict['investimento']:.2f} (CPM: R$ {cenario_dict['cpm']:.2f}).
        VENDA ESPERADA: R$ {cenario_dict['preco_venda']:.2f} (Lucro: R$ {cenario_dict['lucro']:.2f}, ROI: {cenario_dict['roi']:.1f}%).
        MERCADO: Preço médio hoje é R$ {dados_mercado.get(cenario_dict['programa'], 0):.2f}.
        
        Sua resposta deve ser formatada em HTML simples para ficar bonita no app.
        Use tags <b> para negrito.
        Responda em 3 tópicos curtos:
        1. Veredito sobre o Preço de Venda.
        2. Análise do Risco vs Retorno.
        3. Conclusão Final (Comece com ✅, ⚠️ ou ❌).
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
        ''', (datetime.now().strftime("%d/%m %H:%M"), dados['programa'], dados['investimento'], dados['pontos'], dados['preco_venda'], dados['lucro'], dados['roi']))
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

# --- 3. MONITOR DE OPORTUNIDADES ---
@st.cache_data(ttl=1800)
def buscar_oportunidades():
    """Busca as últimas notícias de milhas."""
    url = "https://www.melhorescartoes.com.br/category/programas-de-fidelidade"
    headers = {"User-Agent": "Mozilla/5.0"}
    oportunidades = []
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tenta encontrar os títulos das notícias
        artigos = soup.find_all('h2') + soup.find_all('h3')
        
        for artigo in artigos[:10]:
            titulo = artigo.get_text().strip()
            # Encontra o link dentro do título ou no pai
            link_tag = artigo.find('a')
            if not link_tag:
                link_tag = artigo.parent.find('a')
            
            link = link_tag['href'] if link_tag else "#"
            
            # Filtro inteligente
            keywords = ["bônus", "100%", "compra", "transferência", "livelo", "esfera", "tudoazul", "latam", "smiles"]
            if any(k in titulo.lower() for k in keywords):
                if not any(op['link'] == link for op in oportunidades): # Evita duplicatas
                    oportunidades.append({"titulo": titulo, "link": link})
                
    except:
        pass
        
    return oportunidades[:5] # Retorna as top 5

# --- 4. DADOS AUXILIARES ---
@st.cache_data(ttl=3600)
def obter_cotacoes():
    return {"Smiles": 17.60, "LatamPass": 23.20, "TudoAzul": 19.80}

# --- 5. INTERFACE PRINCIPAL ---
def main():
    db = PortfolioManager()
    cotacoes = obter_cotacoes()
    
    # Gerenciamento Seguro da API Key
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        # Fallback para teste local se não tiver secrets
        api_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    analista = AIAnalyst(api_key)

    # --- TOPO: TÍTULO E NOTÍCIAS ---
    st.title("✈️ MilhasApp")
    
    with st.expander("🔥 Radar de Promoções (Hoje)", expanded=True):
        news = buscar_oportunidades()
        if news:
            for item in news:
                st.markdown(f"👉 **[{item['titulo']}]({item['link']})**")
        else:
            st.info("Nenhuma promoção bombástica detectada agora.")

    # --- ÁREA DE AÇÃO (SIMULADOR) ---
    st.markdown("---")
    st.subheader("💰 Simulador de Lucro")
    
    # Inputs otimizados para mobile
    c1, c2 = st.columns(2)
    programa = c1.selectbox("Programa", ["Smiles", "LatamPass", "TudoAzul"])
    bonus = c2.selectbox("Bônus %", [100, 90, 80, 70, 60, 0])
    
    investimento = st.number_input("Investimento Total (R$)", value=3500.0, step=100.0)
    
    c3, c4 = st.columns(2)
    pontos_compra = c3.number_input("Pontos Base", value=100000, step=1000)
    
    preco_ref = cotacoes.get(programa, 20.00)
    preco_venda = c4.number_input("Venda (R$)", value=preco_ref, step=0.10)

    # Cálculos
    total_milhas = pontos_compra * (1 + (bonus / 100))
    lucro = ((total_milhas/1000) * preco_venda) - investimento
    roi = (lucro / investimento) * 100 if investimento > 0 else 0
    cpm = investimento / (total_milhas / 1000) if total_milhas > 0 else 0

    cenario = {
        "programa": programa, "investimento": investimento, "pontos": total_milhas,
        "cpm": cpm, "preco_venda": preco_venda, "lucro": lucro, "roi": roi
    }

    # --- RESULTADOS VISUAIS (CORRIGIDO) ---
    st.markdown("<br>", unsafe_allow_html=True) # Espacinho
    
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta=f"{roi:.1f}% ROI")
    kpi2.metric("Custo Milheiro", f"R$ {cpm:.2f}", delta="CPM", delta_color="off")
    
    # --- BOTÕES DE AÇÃO ---
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    
    if b1.button("✨ IA Analisar", type="primary"):
        with st.spinner("Analisando..."):
            parecer = analista.analisar_cenario(cenario, cotacoes)
            # Caixa de resposta da IA com cor fixa para leitura
            st.markdown(f"""
            <div style="background-color:#F0F2F6; color:#1E1E1E; padding:15px; border-radius:10px; border-left:5px solid #00C853; margin-top:10px; font-family:sans-serif;">
            {parecer}
            </div>
            """, unsafe_allow_html=True)
            
    if b2.button("💾 Salvar"):
        db.salvar_operacao(cenario)
        st.toast("Salvo na Carteira!", icon="✅")

    # --- CARTEIRA ---
    st.markdown("---")
    with st.expander("📂 Minha Carteira"):
        df = db.listar_carteira()
        if not df.empty:
            # Mostra tabela simples
            st.dataframe(
                df[["data_registro", "programa", "lucro_projetado", "roi_percentual"]], 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "data_registro": "Data",
                    "lucro_projetado": st.column_config.NumberColumn("Lucro", format="R$ %.2f"),
                    "roi_percentual": st.column_config.NumberColumn("ROI", format="%.1f%%")
                }
            )
            
            # Botão de limpeza
            if st.button("🗑️ Limpar Último Registro"):
                last_id = df.iloc[0]['id']
                db.excluir_operacao(int(last_id))
                st.rerun()
        else:
            st.info("Nenhuma operação salva ainda.")

if __name__ == "__main__":
    main()