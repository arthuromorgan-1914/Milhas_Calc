import streamlit as st
import pandas as pd
import requests
import sqlite3
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="MilhasBot AI | Advisor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 1. MÓDULO DE IA (GEMINI 1.5 FLASH) ---
class AIAnalyst:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # ATUALIZAÇÃO: Usando a versão 2.5 encontrada no diagnóstico
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except Exception as e:
                st.error(f"Erro ao configurar API: {e}")

    def analisar_cenario(self, cenario_dict, dados_mercado, carteira_df):
        """Envia os dados matemáticos para a IA gerar um parecer estratégico."""
        if not self.api_key:
            return "⚠️ Insira sua API Key na barra lateral para ativar a IA."
        
        # Contexto da Carteira Atual
        total_investido = carteira_df['investimento'].sum() if not carteira_df.empty else 0
        risco_carteira = "Alto" if total_investido > 10000 else "Baixo"

        # Engenharia de Prompt Otimizada
        prompt = f"""
        Atue como um analista financeiro sênior especializado em Milhas Aéreas e Arbitragem.
        Analise a viabilidade desta operação de compra e venda de pontos:

        DADOS DA OPERAÇÃO:
        - Programa: {cenario_dict['programa']}
        - Investimento: R$ {cenario_dict['investimento']:.2f}
        - Custo do Milheiro (CPM): R$ {cenario_dict['cpm']:.2f}
        - Preço de Venda Esperado: R$ {cenario_dict['preco_venda']:.2f}
        - Lucro Líquido Projetado: R$ {cenario_dict['lucro']:.2f}
        - ROI (Retorno): {cenario_dict['roi']:.2f}%
        
        CENÁRIO DE MERCADO (Preços Médios Hoje):
        - Smiles: R$ {dados_mercado.get('Smiles', 0):.2f}
        - Latam: R$ {dados_mercado.get('LatamPass', 0):.2f}
        - TudoAzul: R$ {dados_mercado.get('TudoAzul', 0):.2f}

        CONTEXTO DO USUÁRIO:
        - O usuário já tem R$ {total_investido:.2f} investidos em outras operações.

        SUA TAREFA:
        1. Compare o preço de venda esperado com o mercado real (se estiver muito acima, alerte).
        2. Avalie se o ROI justifica o risco e o tempo de espera (custo de oportunidade).
        3. Dê um veredito final curto.

        Formato da resposta: Curta, direta, em tópicos (markdown). Máximo 4 linhas.
        Comece com um Emoji de Veredito (✅, ⚠️ ou ❌).
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Erro na análise de IA: {str(e)}. Verifique se a API Key está correta."

# --- 2. GERENCIAMENTO DE BANCO DE DADOS (SQLite) ---
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
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M"), dados['programa'], dados['investimento'], dados['pontos'], dados['preco_venda'], dados['lucro'], dados['roi']))
        conn.commit()
        conn.close()

    def listar_carteira(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_name)
        try:
            df = pd.read_sql_query("SELECT * FROM operacoes ORDER BY id DESC", conn)
        except:
            df = pd.DataFrame()
        conn.close()
        return df
    
    def excluir_operacao(self, id_op):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM operacoes WHERE id = ?", (id_op,))
        conn.commit()
        conn.close()

# --- 3. SCRAPER DE MERCADO (Com Cache e Resiliência) ---
@st.cache_data(ttl=3600)
def buscar_cotacoes_mercado() -> Dict[str, float]:
    url = "https://www.melhorescartoes.com.br/cotacao-milhas"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    # Valores padrão (Fallback) caso o site esteja fora do ar
    cotacoes = {"Smiles": 17.50, "LatamPass": 23.00, "TudoAzul": 19.50} 
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tabelas = soup.find_all('table')
            for tabela in tabelas:
                texto_tabela = tabela.get_text().lower()
                if "smiles" in texto_tabela or "latam" in texto_tabela:
                    rows = tabela.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) > 1:
                            prog = cols[0].get_text().strip().lower()
                            val_str = cols[1].get_text().replace('R$', '').replace(',', '.').strip()
                            try:
                                val = float(val_str)
                                if "smiles" in prog: cotacoes["Smiles"] = val
                                elif "latam" in prog: cotacoes["LatamPass"] = val
                                elif "azul" in prog: cotacoes["TudoAzul"] = val
                            except: continue
    except Exception as e:
        print(f"Erro ao buscar cotações: {e}")
        
    return cotacoes

# --- 4. INTERFACE PRINCIPAL (UI) ---
def main():
    # Inicializa gerenciadores
    db = PortfolioManager()
    
    # --- BARRA LATERAL (Configurações) ---
    st.sidebar.title("⚙️ Configurações")
    
    # Input da API Key
    api_key = st.sidebar.text_input("Gemini API Key", type="password", placeholder="Cole sua chave aqui...")
    if not api_key:
        st.sidebar.warning("Cole sua chave API para ativar a IA.")
        st.sidebar.markdown("[Obter Chave Grátis](https://aistudio.google.com/app/apikey)")
    
    analista = AIAnalyst(api_key)
    
    st.sidebar.markdown("---")
    st.sidebar.info("Dica: Use o modelo Gemini 1.5 Flash para respostas rápidas.")

    # --- TELA PRINCIPAL ---
    st.title("✈️ MilhasBot AI: Arbitragem Inteligente")
    st.markdown("Simule operações, analise riscos com IA e gerencie sua carteira de milhas.")
    
    # Busca dados de mercado
    with st.spinner("Atualizando cotações do mercado..."):
        cotacoes = buscar_cotacoes_mercado()
    
    # --- INPUTS DA SIMULAÇÃO ---
    st.subheader("1. Simular Nova Operação")
    
    col1, col2, col3 = st.columns(3)
    programa = col1.selectbox("Programa de Fidelidade", list(cotacoes.keys()))
    investimento = col2.number_input("Investimento Total (R$)", value=3500.0, step=100.0)
    bonus = col3.slider("Bônus Transferência (%)", 0, 150, 100)
    
    col4, col5 = st.columns(2)
    pontos_compra = col4.number_input("Pontos Comprados (Base)", value=100000)
    
    # Sugestão de preço baseada no scraper
    preco_sugerido = cotacoes.get(programa, 20.00)
    preco_venda = col5.number_input(f"Preço de Venda Esperado (R$)", value=preco_sugerido, step=0.10, help=f"Média atual: R$ {preco_sugerido:.2f}")

    # --- CÁLCULOS MATEMÁTICOS ---
    total_milhas = pontos_compra * (1 + (bonus / 100))
    cpm = investimento / (total_milhas / 1000)
    receita = (total_milhas / 1000) * preco_venda
    lucro = receita - investimento
    roi = (lucro / investimento) * 100 if investimento > 0 else 0
    
    cenario_dados = {
        "programa": programa,
        "investimento": investimento,
        "pontos": total_milhas,
        "cpm": cpm,
        "preco_venda": preco_venda,
        "lucro": lucro,
        "roi": roi
    }

    # --- EXIBIÇÃO DE RESULTADOS ---
    st.divider()
    
    # Cartões de Métricas (KPIs)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CPM (Custo Milheiro)", f"R$ {cpm:.2f}", delta="-Bom" if cpm < 15 else "Normal", delta_color="inverse")
    c2.metric("Lucro Estimado", f"R$ {lucro:.2f}", delta=f"{roi:.1f}%")
    c3.metric("Milhas Totais", f"{int(total_milhas):,}")
    c4.metric("Ref. Mercado", f"R$ {cotacoes.get(programa, 0):.2f}", delta=f"{(preco_venda - cotacoes.get(programa,0)):.2f}")

    # --- BOTÃO MÁGICO DA IA ---
    st.subheader("🧠 Análise do Consultor IA")
    
    col_ia, col_save = st.columns([2, 1])
    
    with col_ia:
        if st.button("✨ Analisar Viabilidade com IA", type="primary"):
            if not api_key:
                st.error("⚠️ Você precisa colar a API Key na barra lateral esquerda primeiro.")
            else:
                with st.spinner("O Consultor IA está analisando os números..."):
                    carteira_atual = db.listar_carteira()
                    parecer = analista.analisar_cenario(cenario_dados, cotacoes, carteira_atual)
                    st.success("Análise Concluída:")
                    st.markdown(f"""
                    <div style="background-color: #F0F2F6; color: #1E1E1E; padding: 15px; border-radius: 8px; border-left: 5px solid #00C853;font-family: sans-serif;">
                        {parecer}
                    </div>
                    """, unsafe_allow_html=True)
    
    with col_save:
        if st.button("💾 Salvar na Carteira"):
            db.salvar_operacao(cenario_dados)
            st.toast("Operação salva com sucesso!", icon="✅")
            st.rerun()

    # --- HISTÓRICO E CARTEIRA ---
    st.divider()
    st.subheader("📂 Minha Carteira de Operações")
    
    df = db.listar_carteira()
    if not df.empty:
        # Métricas Globais da Carteira
        total_lucro_cart = df["lucro_projetado"].sum()
        total_inv_cart = df["investimento"].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Lucro Acumulado Global", f"R$ {total_lucro_cart:.2f}")
        m2.metric("Total Investido", f"R$ {total_inv_cart:.2f}")

        # Tabela
        st.dataframe(
            df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "lucro_projetado": st.column_config.NumberColumn("Lucro", format="R$ %.2f"),
                "roi_percentual": st.column_config.NumberColumn("ROI", format="%.1f%%"),
                "data_registro": "Data",
                "programa": "Programa",
            }
        )
        
        # Botão de excluir (Demo)
        with st.expander("Gerenciar Registros"):
            id_to_delete = st.number_input("ID para excluir", min_value=0, step=1)
            if st.button("🗑️ Excluir Registro"):
                db.excluir_operacao(id_to_delete)
                st.rerun()
    else:
        st.info("Sua carteira está vazia. Faça uma simulação acima e clique em 'Salvar'.")

if __name__ == "__main__":
    main()