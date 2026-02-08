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
    initial_sidebar_state="expanded" # Aberto para ver o perfil
)

# --- CSS (VISUAL MOBILE & CORREÇÃO DE CORES) ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 5rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        .stButton button {
            width: 100%;
            border-radius: 12px;
            height: 3.5em;
            font-weight: bold;
            border: none;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        
        /* CORREÇÃO DAS CAIXAS DE MÉTRICAS */
        div[data-testid="stMetric"] {
            background-color: #F8F9FA !important;
            border: 1px solid #E9ECEF;
            padding: 15px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        div[data-testid="stMetric"] label {
            color: #495057 !important; 
            font-size: 0.9rem !important;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            color: #000000 !important;
            font-weight: 800 !important;
        }
        div[data-testid="stMetricDelta"] {
            background-color: rgba(0,0,0,0.05);
            border-radius: 5px;
            padding: 2px 5px;
            font-weight: bold;
        }
    </style>
""", unsafe_allow_html=True)

# --- 1. MÓDULO DE IA ---
class AIAnalyst:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except:
                self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analisar_cenario(self, cenario_dict, dados_mercado):
        if not self.api_key:
            return "⚠️ Configure a API Key."
        
        prompt = f"""
        Consultor Milhas. Direto.
        OPERAÇÃO: {cenario_dict['programa']}, Invest: R${cenario_dict['investimento']:.0f}, Venda: R${cenario_dict['preco_venda']:.2f}, Lucro: R${cenario_dict['lucro']:.0f}.
        MERCADO: Média {cenario_dict['programa']} é R$ {dados_mercado.get(cenario_dict['programa'], 0):.2f}.
        
        Responda em HTML simples (<b>negrito</b>).
        1. Preço de venda realista?
        2. Risco compensa?
        3. Veredito (Emoji).
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Erro na IA: {str(e)}"

# --- 2. SCRAPERS ---
@st.cache_data(ttl=3600)
def buscar_cotacoes_mercado():
    url = "https://www.melhorescartoes.com.br/cotacao-milhas"
    headers = {"User-Agent": "Mozilla/5.0"}
    cotacoes = {"Smiles": 17.00, "LatamPass": 23.00, "TudoAzul": 19.00}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        tabelas = soup.find_all('table')
        for tabela in tabelas:
            txt = tabela.get_text().lower()
            if "smiles" in txt or "latam" in txt:
                rows = tabela.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        prog = cols[0].get_text().strip().lower()
                        val_str = cols[1].get_text().replace('R$', '').replace('.', '').replace(',', '.').strip()
                        try:
                            val = float(re.findall(r"\d+\.\d+", val_str)[0])
                            if "smiles" in prog: cotacoes["Smiles"] = val
                            elif "latam" in prog: cotacoes["LatamPass"] = val
                            elif "azul" in prog: cotacoes["TudoAzul"] = val
                        except: continue
    except: pass
    return cotacoes

@st.cache_data(ttl=1800)
def buscar_oportunidades():
    url = "https://www.melhorescartoes.com.br/category/programas-de-fidelidade"
    headers = {"User-Agent": "Mozilla/5.0"}
    ops = []
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all(['h2', 'h3'])[:10]:
            t = a.get_text().strip()
            l_tag = a.find('a') if a.find('a') else a.parent.find('a')
            l = l_tag['href'] if l_tag else "#"
            ks = ["bônus", "100%", "compra", "transferência", "livelo", "esfera"]
            if any(k in t.lower() for k in ks) and not any(o['link']==l for o in ops):
                ops.append({"titulo": t, "link": l})
    except: pass
    return ops[:5]

# --- 3. BANCO DE DADOS (COM SUPORTE A PERFIL) ---
class PortfolioManager:
    def __init__(self, db_name="milhas_portfolio.db"):
        self.db_name = db_name
        self._init_db()
        self._migrate_db() # Garante que a coluna usuario exista
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_registro TEXT,
                usuario TEXT,
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

    def _migrate_db(self):
        """Adiciona a coluna usuario em bancos antigos se não existir"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            # Tenta selecionar a nova coluna. Se der erro, ela não existe.
            cursor.execute("SELECT usuario FROM operacoes LIMIT 1")
        except sqlite3.OperationalError:
            # Coluna não existe, vamos criar
            cursor.execute("ALTER TABLE operacoes ADD COLUMN usuario TEXT DEFAULT 'Guilherme'")
            conn.commit()
        conn.close()

    def salvar_operacao(self, dados: Dict, usuario: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operacoes (data_registro, usuario, programa, investimento, pontos, preco_venda, lucro_projetado, roi_percentual)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime("%d/%m %H:%M"), usuario, dados['programa'], dados['investimento'], dados['pontos'], dados['preco_venda'], dados['lucro'], dados['roi']))
        conn.commit()
        conn.close()

    def listar_carteira(self, usuario_filtro: str) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_name)
        try:
            # Filtra pelo usuário selecionado
            df = pd.read_sql_query("SELECT * FROM operacoes WHERE usuario = ? ORDER BY id DESC", conn, params=(usuario_filtro,))
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
    # --- BARRA LATERAL (PERFIL) ---
    st.sidebar.title("👤 Perfil")
    usuario_atual = st.sidebar.radio(
        "Quem está usando?",
        ["Guilherme", "Visitante"],
        index=0
    )
    
    st.sidebar.markdown("---")
    
    # API Key Config
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    analista = AIAnalyst(api_key)
    db = PortfolioManager()

    # --- DADOS EXTERNOS ---
    with st.spinner("Carregando mercado..."):
        cotacoes = buscar_cotacoes_mercado()
    
    # --- UI PRINCIPAL ---
    st.title(f"✈️ Olá, {usuario_atual}!")
    st.caption(f"Mercado Hoje: Smiles R${cotacoes.get('Smiles',0)} | Latam R${cotacoes.get('LatamPass',0)}")

    # Radar
    with st.expander("🔥 Radar de Oportunidades", expanded=False):
        news = buscar_oportunidades()
        if news:
            for item in news: st.markdown(f"👉 **[{item['titulo']}]({item['link']})**")
        else: st.info("Sem novidades no momento.")

    # Simulador
    st.markdown("---")
    st.subheader("💰 Simulador")
    
    c1, c2 = st.columns(2)
    prog = c1.selectbox("Programa", ["Smiles", "LatamPass", "TudoAzul"])
    bonus = c2.selectbox("Bônus %", [100, 80, 60, 0])
    inv = st.number_input("Investimento (R$)", value=3500.0, step=50.0)
    
    c3, c4 = st.columns(2)
    pts = c3.number_input("Pontos Base", value=100000, step=1000)
    preco_venda = c4.number_input("Venda (R$)", value=cotacoes.get(prog, 20.0), step=0.1)

    # Cálculos
    total_pts = pts * (1 + (bonus / 100))
    lucro = ((total_pts/1000) * preco_venda) - inv
    roi = (lucro / inv) * 100 if inv > 0 else 0
    cpm = inv / (total_pts / 1000) if total_pts > 0 else 0
    
    cenario = {
        "programa": prog, "investimento": inv, "pontos": total_pts,
        "cpm": cpm, "preco_venda": preco_venda, "lucro": lucro, "roi": roi
    }

    # KPIs
    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2 = st.columns(2)
    k1.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta=f"{roi:.1f}%")
    k2.metric("CPM", f"R$ {cpm:.2f}", delta_color="off")
    
    # Ações
    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    
    if b1.button("✨ IA Analisar", type="primary"):
        with st.spinner("Analisando..."):
            res = analista.analisar_cenario(cenario, cotacoes)
            st.markdown(f"""
            <div style="background-color:#F0F2F6; color:#1E1E1E; padding:15px; border-radius:10px; border-left:5px solid #00C853; margin-top:10px; font-family:sans-serif;">
            {res}
            </div>""", unsafe_allow_html=True)
            
    if b2.button("💾 Salvar na Minha Carteira"):
        # AQUI O SEGREDINHO: Salvamos passando o nome do usuário atual
        db.salvar_operacao(cenario, usuario_atual)
        st.toast(f"Salvo para {usuario_atual}!", icon="✅")

    # Carteira Filtrada
    st.markdown("---")
    with st.expander(f"📂 Carteira de {usuario_atual}"):
        # AQUI O SEGREDINHO 2: Listamos apenas o usuário atual
        df = db.listar_carteira(usuario_atual)
        if not df.empty:
            st.dataframe(
                df[["data_registro", "programa", "lucro_projetado", "roi_percentual"]], 
                hide_index=True, use_container_width=True,
                column_config={"lucro_projetado": st.column_config.NumberColumn("Lucro", format="R$ %.2f")}
            )
            if st.button("🗑️ Apagar Último"):
                db.excluir_operacao(int(df.iloc[0]['id']))
                st.rerun()
        else:
            st.info(f"Nenhuma operação salva para {usuario_atual}.")

if __name__ == "__main__":
    main()