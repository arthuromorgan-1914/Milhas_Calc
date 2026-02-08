import streamlit as st
import pandas as pd
import requests
import sqlite3
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List
import re

# --- CONFIGURAÇÃO DA PÁGINA (MOBILE FIRST) ---
st.set_page_config(
    page_title="MilhasApp Pro",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS (VISUAL MOBILE & CORREÇÃO DE CORES) ---
st.markdown("""
    <style>
        /* 1. Ajuste de Margens para Mobile */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 5rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        
        /* 2. Limpeza Visual */
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* 3. Botões Grandes (Touch Friendly) */
        .stButton button {
            width: 100%;
            border-radius: 12px;
            height: 3.5em;
            font-weight: bold;
            border: none;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        
        /* 4. CORREÇÃO CRÍTICA: Caixas de Métricas (Fundo Claro + Texto Preto) */
        div[data-testid="stMetric"] {
            background-color: #F8F9FA !important;
            border: 1px solid #E9ECEF;
            padding: 15px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        
        /* Título da métrica (ex: "Lucro") em Cinza Escuro */
        div[data-testid="stMetric"] label {
            color: #495057 !important; 
            font-size: 0.9rem !important;
        }
        
        /* Valor da métrica (ex: "R$ 200") em Preto Absoluto */
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #000000 !important;
            font-weight: 800 !important;
        }
        
        /* Delta (Percentual) com fundo suave */
        div[data-testid="stMetricDelta"] {
            background-color: rgba(0,0,0,0.05);
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
                # Tenta usar a versão mais recente e rápida
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except:
                # Fallback se a 2.5 não estiver disponível na região
                self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analisar_cenario(self, cenario_dict, dados_mercado):
        if not self.api_key:
            return "⚠️ Configure a API Key nos 'Secrets' do Streamlit."
        
        prompt = f"""
        Você é um consultor financeiro especialista em Milhas. Seja direto.
        
        DADOS DA OPERAÇÃO:
        - Programa: {cenario_dict['programa']}
        - Investimento: R$ {cenario_dict['investimento']:.2f} (CPM: R$ {cenario_dict['cpm']:.2f})
        - Venda Esperada: R$ {cenario_dict['preco_venda']:.2f}
        - Lucro: R$ {cenario_dict['lucro']:.2f} (ROI: {cenario_dict['roi']:.1f}%)
        
        MERCADO HOJE (Referência):
        - Preço médio de venda do {cenario_dict['programa']}: R$ {dados_mercado.get(cenario_dict['programa'], 0):.2f}
        
        SUA ANÁLISE (Responda em HTML simples, sem markdown):
        Use tags <b> para negrito e <br> para pular linha.
        1. O preço de venda de R$ {cenario_dict['preco_venda']} é realista?
        2. O risco vale o retorno de R$ {cenario_dict['lucro']}?
        3. Veredito final (Comece com um Emoji).
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Erro na IA: {str(e)}"

# --- 2. SCRAPERS (PREÇOS E NOTÍCIAS) ---

@st.cache_data(ttl=3600) # Atualiza preços a cada 1 hora
def buscar_cotacoes_mercado():
    """Busca média de preço em site de referência (Melhores Cartões)."""
    url = "https://www.melhorescartoes.com.br/cotacao-milhas"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    # Valores de segurança (caso o site caia)
    cotacoes = {"Smiles": 17.00, "LatamPass": 23.00, "TudoAzul": 19.00}
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Procura tabelas na página
            tabelas = soup.find_all('table')
            
            for tabela in tabelas:
                texto_tabela = tabela.get_text().lower()
                # Se a tabela fala de milhas, tenta ler
                if "smiles" in texto_tabela or "latam" in texto_tabela:
                    rows = tabela.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) > 1:
                            prog = cols[0].get_text().strip().lower()
                            # Limpa o preço (tira R$, troca virgula por ponto)
                            preco_str = cols[1].get_text().replace('R$', '').replace('.', '').replace(',', '.').strip()
                            
                            try:
                                # Pega apenas o primeiro número se houver faixa (ex: "17.50 - 18.00")
                                preco_val = float(re.findall(r"\d+\.\d+", preco_str)[0])
                                
                                if "smiles" in prog: cotacoes["Smiles"] = preco_val
                                elif "latam" in prog: cotacoes["LatamPass"] = preco_val
                                elif "azul" in prog: cotacoes["TudoAzul"] = preco_val
                            except:
                                continue
    except:
        pass # Mantém os valores padrão silenciosamente em caso de erro
        
    return cotacoes

@st.cache_data(ttl=1800) # Atualiza notícias a cada 30 min
def buscar_oportunidades():
    """Busca manchetes de promoções."""
    url = "https://www.melhorescartoes.com.br/category/programas-de-fidelidade"
    headers = {"User-Agent": "Mozilla/5.0"}
    oportunidades = []
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        artigos = soup.find_all(['h2', 'h3'])
        
        for artigo in artigos[:12]:
            titulo = artigo.get_text().strip()
            link_tag = artigo.find('a') if artigo.find('a') else artigo.parent.find('a')
            link = link_tag['href'] if link_tag else "#"
            
            keywords = ["bônus", "100%", "compra", "transferência", "livelo", "esfera"]
            if any(k in titulo.lower() for k in keywords):
                if not any(op['link'] == link for op in oportunidades):
                    oportunidades.append({"titulo": titulo, "link": link})
    except: pass
    return oportunidades[:5]

# --- 3. GERENCIAMENTO DE BANCO DE DADOS ---
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

# --- 4. INTERFACE PRINCIPAL ---
def main():
    db = PortfolioManager()
    
    # 1. Configuração de Segurança (API Key)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    analista = AIAnalyst(api_key)

    # 2. Busca Dados Externos (Cotações e Notícias)
    with st.spinner("Atualizando mercado..."):
        cotacoes = buscar_cotacoes_mercado()
    
    # --- CABEÇALHO ---
    st.title("✈️ MilhasApp")
    st.caption(f"Cotações Atualizadas: Smiles (R$ {cotacoes.get('Smiles',0)}) | Latam (R$ {cotacoes.get('LatamPass',0)})")

    # --- RADAR DE PROMOÇÕES ---
    with st.expander("🔥 Radar de Oportunidades (Ao Vivo)", expanded=False):
        news = buscar_oportunidades()
        if news:
            for item in news:
                st.markdown(f"👉 **[{item['titulo']}]({item['link']})**")
        else:
            st.info("Nenhuma promoção bombástica agora.")

    # --- SIMULADOR ---
    st.markdown("---")
    st.subheader("💰 Novo Cálculo")
    
    c1, c2 = st.columns(2)
    programa = c1.selectbox("Programa", ["Smiles", "LatamPass", "TudoAzul"])
    bonus = c2.selectbox("Bônus %", [100, 90, 80, 70, 60, 0])
    
    investimento = st.number_input("Investimento (R$)", value=3500.0, step=50.0)
    
    c3, c4 = st.columns(2)
    pontos_compra = c3.number_input("Pontos Base", value=100000, step=1000)
    
    # O Input de Venda agora vem preenchido com o valor raspado da internet
    preco_ref = cotacoes.get(programa, 20.00)
    preco_venda = c4.number_input("Venda (R$)", value=preco_ref, step=0.10, help=f"Média Mercado: R$ {preco_ref}")

    # Cálculos
    total_milhas = pontos_compra * (1 + (bonus / 100))
    lucro = ((total_milhas/1000) * preco_venda) - investimento
    roi = (lucro / investimento) * 100 if investimento > 0 else 0
    cpm = investimento / (total_milhas / 1000) if total_milhas > 0 else 0

    cenario = {
        "programa": programa, "investimento": investimento, "pontos": total_milhas,
        "cpm": cpm, "preco_venda": preco_venda, "lucro": lucro, "roi": roi
    }

    # --- RESULTADOS (Com CSS corrigido) ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    kpi1, kpi2 = st.columns(2)
    kpi1.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta=f"{roi:.1f}% ROI")
    kpi2.metric("Custo Milheiro", f"R$ {cpm:.2f}", delta="CPM", delta_color="off")
    
    # --- BOTÕES ---
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    
    if b1.button("✨ IA Analisar", type="primary"):
        with st.spinner("Analisando..."):
            parecer = analista.analisar_cenario(cenario, cotacoes)
            # Caixa de resposta com estilo inline para garantir leitura
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
            if st.button("🗑️ Limpar Último"):
                last_id = df.iloc[0]['id']
                db.excluir_operacao(int(last_id))
                st.rerun()
        else:
            st.info("Nenhuma operação salva.")

if __name__ == "__main__":
    main()