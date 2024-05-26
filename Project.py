import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import math
import locale

locale.setlocale(locale.LC_ALL, '')


@st.cache_data
#ler o arquivo e formatar#
def ler_arquivo_excel(arquivo_excel):
    df = pd.read_excel(arquivo_excel, sheet_name="Planilha1",
                       parse_dates=["Início Agendado", "Término Agendado",
                                    "Início da Linha de Base", "Término da linha de base"],
                       date_parser=lambda x: pd.to_datetime(x, format='%d/%m/%y'))
    df.rename(columns={"Início da Linha de Base": "Início BL", "Término da linha de base": "Término BL", "Duração da Linha de Base": "Duração BL",
                       "Margem de atraso permitida":"Folga"}, inplace=True)
    df = df.apply(lambda col: col.str.replace('dias', '') if col.dtype == 'object' else col)
    df[['Predecessoras', 'Sucessoras']] = df[['Predecessoras', 'Sucessoras']].astype(str)
    df[['Duração BL']] = df[['Duração BL']].astype(int)
    df = df.query("Resumo == 'Não'")
    df['Custo Diário'] = df['Custo'] / df['Duração BL']

    return df

@st.cache_data
# Incluir Feriados#
def selecionar_feriados(feriados_texto):
    feriados = []
    for data_texto in feriados_texto.split('\n'):
        data_texto = data_texto.strip()
        if data_texto:
            try:
                feriados.append(pd.to_datetime(data_texto, format='%d/%m/%Y'))
            except ValueError:
                st.error(f"A data '{data_texto}' está em um formato inválido. Por favor, use o formato 'DD/MM/YYYY'.")
    return feriados

#Criar Curva S
def criar_curva_s(dataframe, agrupamento, S30, S50, S70):
    if agrupamento == 'Mês':
        curva_s_agrupado = dataframe.groupby(pd.Grouper(freq='M')).sum()
        curva_s_agrupado.index = curva_s_agrupado.index.strftime('%m/%y')
        N = len(curva_s_agrupado)
    elif agrupamento == 'Semana':
        curva_s_agrupado = dataframe.groupby(pd.Grouper(freq='W-MON')).sum()
        curva_s_agrupado.index = curva_s_agrupado.index.strftime('%d/%m/%y')
        N = len(curva_s_agrupado)
    else:
        curva_s_agrupado = pd.DataFrame()  # Retornar um DataFrame vazio se o agrupamento não for reconhecido


    # Calcular a nova coluna usando a fórmula 1 - [1 - (n/N)^{log(I)}]^S
    curva_s_agrupado['n'] = range(0, N)
    curva_s_agrupado['Curva30'] = curva_s_agrupado['n'].apply(lambda n: (1-((1-((n/(N-1))**(math.log10(30))))**S30))*100)
    curva_s_agrupado['Curva50'] = curva_s_agrupado['n'].apply(lambda n: (1 - ((1 - ((n / (N-1)) ** (math.log10(50)))) ** S50)) * 100)
    curva_s_agrupado['Curva70'] = curva_s_agrupado['n'].apply(lambda n: (1 - ((1 - ((n / (N-1)) ** (math.log10(70)))) ** S70)) * 100)

    # Calcular o percentual acumulado
    curva_s_agrupado['% Acum.'] = curva_s_agrupado['%'].cumsum()

    # Formatar os valores monetários
    curva_s_agrupado['Custo Total '] = curva_s_agrupado['Custo Total'].apply(
        lambda x: locale.currency(x, grouping=True))
    # Formatar as colunas de % e % Acum.
    curva_s_agrupado['% '] = curva_s_agrupado['%'].apply(lambda x: f"{x:.1f}%")
    curva_s_agrupado['% Acum. '] = curva_s_agrupado['% Acum.'].apply(lambda x: f"{x:.1f}%")
    curva_s_agrupado['%C30'] = curva_s_agrupado['Curva30'].apply(lambda x: f"{x:.1f}%")
    curva_s_agrupado['%C50'] = curva_s_agrupado['Curva50'].apply(lambda x: f"{x:.1f}%")
    curva_s_agrupado['%C70'] = curva_s_agrupado['Curva70'].apply(lambda x: f"{x:.1f}%")

    return curva_s_agrupado


def processar_dados(arquivo_excel, feriados_texto, agrupamento_opcao, S30, S50, S70):
    if arquivo_excel is not None:
        # Ler o arquivo Excel e preencher valores ausentes na coluna EDT com uma string vazia
        df = ler_arquivo_excel(arquivo_excel)

        # Converter a coluna "Margem de atraso permitida" para numérico
        df['Folga'] = pd.to_numeric(df['Folga'], errors='coerce')

        # Armazenar as datas de feriado em cache
        feriados = selecionar_feriados(feriados_texto)

        # Criar um intervalo de datas considerando apenas os dias úteis (de segunda a sexta-feira)
        datas_uteis = pd.date_range(start=df['Início BL'].min(), end=df['Término BL'].max(), freq='B')

        # Extendendo o intervalo em uma semana ou um mês
        if agrupamento_opcao == 'Mês':
            datas_uteis = pd.date_range(start=df['Início BL'].min() - pd.DateOffset(months=1),
                                        end=df['Término BL'].max(), freq='B')
        elif agrupamento_opcao == 'Semana':
            datas_uteis = pd.date_range(start=df['Início BL'].min() - pd.DateOffset(weeks=1),
                                        end=df['Término BL'].max(), freq='B')

        # Criar o DataFrame DataS usando o intervalo de datas úteis
        DataS = pd.DataFrame(index=datas_uteis)

        for index, row in df.iterrows():
            data_inicio = row['Início BL']
            data_termino = row['Término BL']
            tarefa = row['Nome da tarefa'].strip()  # Remover espaços extras no nome da tarefa
            custo_total = row['Custo']
            custo_diario = row['Custo Diário']

            # Verificar se a coluna já existe em DataS
            if tarefa not in DataS.columns:
                DataS[tarefa] = 0

            datas_tarefa = pd.date_range(start=data_inicio, end=data_termino, freq='B')  # Apenas dias úteis
            custos_diarios = [custo_diario] * len(datas_tarefa)

            for data in datas_tarefa:
                # Verificar se a data está dentro do intervalo desejado e não está na lista de feriados
                if data not in feriados:
                    DataS.loc[data, tarefa] += custo_diario

            # Calcular a soma dos custos diários por dia para todas as tarefas
        CurvaS = DataS.sum(axis=1).reset_index()
        CurvaS.columns = ['Data', 'Custo Total']
        CurvaS['Data'] = pd.to_datetime(CurvaS['Data'], format='%d.%m.%y')  # Corrigir o formato da data
        CurvaS.set_index('Data', inplace=True)
        custo_total = CurvaS['Custo Total'].sum()
        CurvaS['%'] = round((CurvaS['Custo Total'] / custo_total) * 100, 2)

        # Criar a CurvaS agrupada de acordo com a opção selecionada
        CurvaS_agrupado = criar_curva_s(CurvaS, agrupamento_opcao, S30, S50, S70).round(1)

        return CurvaS_agrupado
    else:
        return None

def caminho_critico_com_gantt(dataframe):
    # Filtrar apenas as tarefas críticas
    tarefas_criticas = dataframe[dataframe['Crítica'] == 'Sim']

    # Selecionar as colunas desejadas
    colunas_desejadas = ['Nome da tarefa', 'Início BL', 'Término BL',
                         'Duração', 'Quant. Prev.', 'Produtividade']

    # Ordenar as tarefas por data de início
    tarefas_criticas = tarefas_criticas.sort_values(by='Início BL')

    # Formatar as datas de início e término
    tarefas_criticas['Início BL'] = pd.to_datetime(tarefas_criticas['Início BL'], format='%d.%m.%y').dt.date
    tarefas_criticas['Término BL'] = pd.to_datetime(tarefas_criticas['Término BL'], format='%d.%m.%y').dt.date

    # Criar uma nova tabela com as colunas desejadas
    tabela_critica = tarefas_criticas[colunas_desejadas]

    # Obter a ordem das tarefas
    order = tarefas_criticas['Nome da tarefa'].tolist()
    order.reverse()

    # Plotar o gráfico de Gantt
    fig = px.timeline(tarefas_criticas, x_start='Início BL', x_end='Término BL',
                      y='Nome da tarefa',
                      labels={'Início BL': 'Início', 'Término BL': 'Término'},
                      color_discrete_sequence=['#0068C9'])

    # Definir a ordem das tarefas no eixo Y
    fig.update_yaxes(categoryorder='array', categoryarray=order)
    # Ajustar a legibilidade dos rótulos de data
    fig.update_layout(xaxis=dict(tickformat="%d-%m-%y"))


    # Ajustar a largura das barras para aumentar o espaçamento
    fig.update_layout(
        xaxis_title='Data',
        yaxis_title='Tarefa',
        autosize=True,  # Permitir que o gráfico ajuste automaticamente seu tamanho
        width=1400,  # Define a largura do gráfico como None para ajustar automaticamente à largura do container
        height=600,  # Ajuste a altura conforme necessário

    )


    return tabela_critica, fig

# Função para calcular indicadores
def calcular_indicadores(df):
    quant_tarefas = len(df)

    # Contabilizar Leads e Lags
    leads = df['Predecessoras'].apply(lambda x: '+' in x).sum()
    lags = df['Predecessoras'].apply(lambda x: '-' in x).sum()

    # Contabilizar Relationship Types
    relationship_types = df['Predecessoras'].apply(lambda x: all(s not in x for s in ['II', 'IT', 'TT'])).sum()

    # Filtrar linhas onde "Predecessoras" e "Sucessoras" estão vazias
    linhas_vazias = df[(df['Predecessoras'] == '') & (df['Sucessoras'] == '')]

    # Contar o número de linhas vazias
    logic = len(linhas_vazias)

    # Calcular porcentagens
    leads_pct = (leads / quant_tarefas) * 100
    lags_pct = (lags / quant_tarefas) * 100
    relationship_types_pct = (relationship_types / quant_tarefas) * 100
    logic_pct = (logic / quant_tarefas) * 100

    # Calcular Data de Início, Data de Término e Duração
    data_inicio = df['Início BL'].min()
    data_termino = df['Término BL'].max()
    duracao_total = (data_termino - data_inicio).days

    data_inicio = pd.to_datetime(data_inicio).strftime("%d/%m/%y")
    data_termino = pd.to_datetime(data_termino).strftime("%d/%m/%y")


    return leads_pct, lags_pct, relationship_types_pct, logic_pct, data_inicio, data_termino, duracao_total

# Função para calcular indicadores de alta duração

def calcular_high_duration(df, valor_alta_duracao):
    # Filtrar tarefas com duração alta (> valor_alta_duracao)
    high_duration_tasks = df[df['Duração BL'] > valor_alta_duracao]

    # Calcular o indicador High Duration
    high_duration_indicator = (len(high_duration_tasks) / len(df)) * 100

    # Exibir o indicador High Duration
    st.subheader(":blue[Índice de Alta Duração:]")
    st.metric(":blue[Should be < 5%]", f"{high_duration_indicator:.2f}%", delta=None,)

    # Exibir DataFrame para High Duration Tasks
    st.subheader(":blue[Tarefas de Alta Duração]:")
    if not high_duration_tasks.empty:
        # Convertendo as colunas de data para datetime, se não forem
        high_duration_tasks['Início BL'] = pd.to_datetime(high_duration_tasks['Início BL'],
                                                                        format='%d.%m.%y').dt.date
        high_duration_tasks['Término BL'] = pd.to_datetime(
            high_duration_tasks['Término BL'], format='%d.%m.%y').dt.date
        html_table_high_duration = high_duration_tasks[
            ['Nome da tarefa', 'Início BL', 'Término BL', 'Duração BL']].to_html(index=False, classes=["dataframe"],
                                                                                 justify="center")
        st.write(css_style + html_table_high_duration, unsafe_allow_html=True)

    else:
        st.write("Nenhuma tarefa encontrada com duração alta.")

# Função para calcular indicadores de baixa duração
def calcular_low_duration(df, valor_baixa_duracao):
    # Filtrar tarefas com duração baixa (< valor_baixa_duracao)
    low_duration_tasks = df[df['Duração BL'] < valor_baixa_duracao]

    # Calcular o indicador Low Duration
    low_duration_indicator = (len(low_duration_tasks) / len(df)) * 100

    # Exibir o indicador Low Duration
    st.subheader(":blue[Índice de Baixa Duração:]")
    st.metric("Should be < 10%", f"{low_duration_indicator:.2f}%", delta=None)

    # Exibir DataFrame para Low Duration Tasks
    st.subheader(":blue[Tarefas de Baixa Duração]:")
    if not low_duration_tasks.empty:
        # Convertendo as colunas de data para datetime, se não forem
        low_duration_tasks['Início BL'] = pd.to_datetime(low_duration_tasks['Início BL'], format='%d.%m.%y').dt.date
        low_duration_tasks['Término BL'] = pd.to_datetime(low_duration_tasks['Término BL'], format='%d.%m.%y').dt.date
        html_table_low_duration = low_duration_tasks[
            ['Nome da tarefa', 'Início BL', 'Término BL', 'Duração BL']].to_html(index=False, classes=["dataframe"],
                                                                                 justify="center")
        st.write(css_style + html_table_low_duration, unsafe_allow_html=True)
    else:
        st.write("Nenhuma tarefa encontrada com duração baixa.")

def format_currency(amount):
    return f'R${amount:,.2f}'.replace('.', ',').replace(',', '.', 2)


# Interface do usuário
# Estilo CSS para ajustar o tamanho da fonte e centralizar o texto no cabeçalho e no corpo da tabela
css_style = """
<style>
.dataframe th {
    font-size: 14px;
    text-align: center;
}
.dataframe td {
    font-size: 14px;
    text-align: center;
}
.scrollable-table {
    max-height: 350px;
    overflow-y: scroll;
}
</style>
"""

st.set_page_config(page_title="Análise de Projeto", page_icon=":bar_chart:", layout="wide")
#____________Sidebar
# Personalizando a barra lateral
st.sidebar.title("Menu")
# Upload do arquivo Excel
arquivo_excel = st.sidebar.file_uploader("Faça upload do seu arquivo Excel", type=["xlsx"], key="uploader1")
# Definir os feriados
feriados_texto = st.sidebar.text_area("Feriados (formato: DD/MM/YYYY)", "")
#____________Sidebar


df= ler_arquivo_excel(arquivo_excel)
# Calcular indicadores
leads_pct, lags_pct, relationship_types_pct, logic_pct, data_inicio, data_termino, duracao_total = calcular_indicadores(df)


col1, col2, col3, col4, col5, col6 = st.columns((1, 2, 1, 1, 1.5, 1.5))

with col3:
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 2px; border-radius: 10px; text-align: center; display:
         flex; flex-direction: column; justify-content: center;
         background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -10px 0;">
                <b>Latências -</b>
            </h2>
            <h3 style="color: #0068C9; margin: -5px 0;">{:.2f}%</h3>
            <h4 style="color: #0068C9; font-size: 12px; margin: -10px 0;">
                <b>Should be: = 0%</b>
            </h4>
        </div>
        """.format(leads_pct),
        unsafe_allow_html=True
    )
with col4:
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 2px; border-radius: 10px; text-align: center; display:
            flex; flex-direction: column; justify-content: center;
            background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -10px 0;">
                <b>Latências +</b>
            </h2>
            <h3 style="color: #0068C9; margin: -5px 0;">{:.2f}%</h3>
            <h4 style="color: #0068C9; font-size: 12px; margin: -10px 0;">
                <b>Should be < 5%</b>
            </h4>
        </div>
            """.format(lags_pct),
        unsafe_allow_html=True
    )
with col5:
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 2px; border-radius: 10px; text-align: center; display:
            flex; flex-direction: column; justify-content: center;
            background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -10px 0;">
                <b>Relacionamento TI</b>
            </h2>
            <h3 style="color: #0068C9; margin: -5px 0;">{:.2f}%</h3>
            <h4 style="color: #0068C9; font-size: 12px; margin: -10px 0;">
                <b>Should be > 95%</b>
            </h4>
        </div>  
        """.format(relationship_types_pct),
        unsafe_allow_html=True
    )
with col6:
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 2px; border-radius: 10px; text-align: center; display:
            flex; flex-direction: column; justify-content: center;
            background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -10px 0;">
                <b>Sem Relacionamento</b>
            </h2>
            <h3 style="color: #0068C9; margin: -5px 0;">{:.2f}%</h3>
            <h4 style="color: #0068C9; font-size: 12px; margin: -10px 0;">
                <b>Should be < 5%</b>
            </h4>
        </div>
            """.format(lags_pct),
        unsafe_allow_html=True
    )
with col2:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    Valor_Agregado = df["Custo"].sum()
    Valor_Agregadof = format_currency(Valor_Agregado)
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 5px; border-radius: 10px; text-align: center;
            display: flex; flex-direction: column; justify-content: center;
            background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -7px 0;">
                <b>Valor Agregado</b>
            <h3 style="color: #0068C9;">{}</h3>
        </div>
        """.format(Valor_Agregadof),
        unsafe_allow_html=True
    )
with col1:
    st.markdown(
        """
        <div style="border: 1px inset #468189; padding: 2px; border-radius: 10px; text-align: left; display:
         flex; flex-direction: column; justify-content: center;
         background-color:#F0F0F0;">
            <h2 style="color: #0068C9;font-size: 20px; margin: -10px 0;">
            </h2>
            <h3 style="color: #0068C9; margin: -6px 0;font-size: 16px;">
                Início BL: {Data_Inicio}
            </h3>
            <h3 style="color: #0068C9; margin: -6px 0;font-size: 16px;">
                Término BL: {Data_Termino}
            </h3>
            <h3 style="color: #0068C9; margin: -6px 0;font-size: 16px;">
                Duração: {Duracao_Total} dias
            </h3>
        </div>
        """.format(Data_Inicio=data_inicio, Data_Termino=data_termino, Duracao_Total=duracao_total),
        unsafe_allow_html=True
    )

st.subheader(":blue[Curva S:]")
col1, col2 = st.columns((2.5,1))  # Dividir a tela em duas colunas

with col2:
    # Escolher o agrupamento
    agrupamento_opcao = st.selectbox("Agrupamento:", ["Mês", "Semana"])

    # Definir os valores de S30, S50 e S70
    col3, col4, col5 = st.columns((1, 1, 1))
    with col3:
        S30 = st.selectbox("Valor de S30", options=[1.0, 1.5, 2.0, 2.5, 3.0], index=3)
    with col4:
        S50 = st.selectbox("Valor de S50", options=[1.0, 1.5, 2.0, 2.5, 3.0], index=3)
    with col5:
        S70 = st.selectbox("Valor de S70", options=[1.0, 1.5, 2.0, 2.5, 3.0], index=3)

# Processar os dados e criar a curva S
CurvaS_agrupado = processar_dados(arquivo_excel, feriados_texto, agrupamento_opcao, S30, S50, S70)



with col1:
    # Plotar o gráfico da curva S agrupado por mês
    if CurvaS_agrupado is not None:
        plt.figure(figsize=(12, 6))
        plt.plot(CurvaS_agrupado.index, CurvaS_agrupado['% Acum.'], marker='o', markerfacecolor="#0068C9", label='% Acum.')
        plt.plot(CurvaS_agrupado.index, CurvaS_agrupado['Curva30'], linestyle=":", color='lightpink', label='S30')
        plt.plot(CurvaS_agrupado.index, CurvaS_agrupado['Curva50'], linestyle=":", color='lightgreen', label='S50')
        plt.plot(CurvaS_agrupado.index, CurvaS_agrupado['Curva70'], linestyle=":", color='Lightgray', label='S70')
        plt.xlabel('Data')
        plt.ylabel('% Acum.')
        # Ajustar a densidade dos ticks dependendo do agrupamento selecionado
        if agrupamento_opcao == 'Mês':
            plt.xticks(CurvaS_agrupado.index[::1], rotation=0)
        elif agrupamento_opcao == 'Semana':
            plt.xticks(CurvaS_agrupado.index[::4], rotation=0)
        plt.legend(loc='upper left')
        plt.grid(False)
        plt.box(None)
        # Adicionando rótulos de dados nos pontos
        for i in range(len(CurvaS_agrupado.index)):
            plt.text(CurvaS_agrupado.index[i], CurvaS_agrupado['% Acum.'][i] + 4,
                     f"{CurvaS_agrupado['% Acum.'][i]:.1f}%", ha="center", va="bottom", color="#0068C9",
                     weight="bold")
        st.pyplot(plt)
    else:
        st.write("Por favor, carregue um arquivo Excel para processar os dados.")

with col2:
    # Formatar a coluna "% Acum." para exibir apenas duas casas decimais
    CurvaS_agrupado['% Acum.'] = CurvaS_agrupado['% Acum.'].apply(lambda x: f"{x:.1f}%")
    CurvaS_agrupado['Custo Total'] = CurvaS_agrupado['Custo Total'].apply(lambda x: f"R$ {x:,.0f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    CurvaS_agrupado.rename(columns={"Custo Total": "Custo"}, inplace=True)
    CurvaS_agrupado_selected = CurvaS_agrupado[["% ", "% Acum.","Custo"]]
    # Resetar o índice para que ele seja tratado como uma coluna normal
    CurvaS_agrupado_selected = CurvaS_agrupado_selected.reset_index()
    # Verificar o tipo de agrupamento e ajustar a exibição da tabela
    if agrupamento_opcao == "Semana":
        html_table_curva_s = CurvaS_agrupado_selected.to_html(index=False, classes=["dataframe"], justify="center", escape=False)
        st.write(css_style + '<div class="scrollable-table">' + html_table_curva_s + '</div>', unsafe_allow_html=True)
    else:
        html_table_curva_s = CurvaS_agrupado_selected.to_html(index=False,classes=["dataframe"], justify="center", escape=False)
        st.write(css_style + html_table_curva_s, unsafe_allow_html=True)

# Mostrar as tarefas críticas
tabela_critica, fig_gantt = caminho_critico_com_gantt(df)

valor_x=5

# Converter a coluna 'Folga' para o tipo numérico
df['Folga'] = pd.to_numeric(df['Folga'], errors='coerce')

# Filtrar as tarefas com folga curta
tarefas_folga_curta = df[(df['Folga'] > 0) & (df['Folga'] <= valor_x)]

# Convertendo as colunas de data para datetime, se não forem
tarefas_folga_curta['Início BL'] = pd.to_datetime(tarefas_folga_curta['Início BL'],
                                                  format='%d.%m.%y').dt.date
tarefas_folga_curta['Término BL'] = pd.to_datetime(tarefas_folga_curta['Término BL'],
                                                   format='%d.%m.%y').dt.date

# Selecionar colunas específicas para exibir
colunas_desejadas = ['Nome da tarefa', 'Início BL', 'Término BL',
                     'Folga']
tarefas_folga_curta = tarefas_folga_curta[colunas_desejadas]

# Dividir a tela em duas colunas
col1, col2 = st.columns((1.5, 1))


# Exibir as tarefas críticas em uma coluna
with col1:
    st.subheader(":blue[Tarefas Críticas:]")
    # Converter a tabela em HTML e aplicar estilos CSS
    html_table_critica = tabela_critica.to_html(index=False, classes=["dataframe"], justify="center")
    st.write(css_style + html_table_critica, unsafe_allow_html=True)

# Exibir a interface do usuário e as tarefas com folga curta em outra coluna
with col2:
    st.subheader(":blue[Tarefas com Folga Curta:]")
    # Interface do usuário para selecionar o valor de X (margem de atraso permitida)
    valor_x = st.selectbox("Selecione o valor para folga curta:", options=[1,2,3,4,5,6,7,8,9,10], index=5)
    # Atualizar a filtragem das tarefas com folga curta com o valor de X selecionado
    tarefas_folga_curta = df[(df['Folga'] > 0) & (df['Folga'] <= valor_x)]

    # Convertendo as colunas de data para datetime, se não forem
    tarefas_folga_curta['Início BL'] = pd.to_datetime(tarefas_folga_curta['Início BL'], format='%d.%m.%y').dt.date
    tarefas_folga_curta['Término BL'] = pd.to_datetime(tarefas_folga_curta['Término BL'], format='%d.%m.%y').dt.date

    # Selecionar colunas específicas para exibir
    colunas_desejadas = ['Nome da tarefa', 'Início BL', 'Término BL', 'Folga']
    tarefas_folga_curta = tarefas_folga_curta[colunas_desejadas]

    # Converter a tabela em HTML e aplicar estilos CSS
    html_table_folga_curta = tarefas_folga_curta.to_html(index=False, classes=["dataframe"], justify="center")
    st.write(css_style + html_table_folga_curta, unsafe_allow_html=True)

st.write("")
st.subheader(":blue[Gráfico de Gantt - Tarefas Críticas:]")
st.plotly_chart(fig_gantt)

# Selecionar valores para alta e baixa duração lado a lado
col1, col2 = st.columns(2)

with col1:
    valor_alta_duracao = st.number_input("Digite o valor para alta duração:", value=20, min_value=5, max_value=50,
                                         step=1, format="%d", key="input_inteiro_alta"
                                         )
    calcular_high_duration(df, valor_alta_duracao)
with col2:
    valor_baixa_duracao = st.number_input("Digite o valor para baixa duração:", value=5, min_value=0, max_value=10,
                                         step=1, format="%d", key="input_inteiro_baixa"
                                         )
    calcular_low_duration(df, valor_baixa_duracao)




























