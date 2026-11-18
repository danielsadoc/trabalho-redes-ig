# Trabalho de Redes — IC/UFRJ

**Bufferbloat, controle de congestionamento e a geometria da informação do AIMD**

Material de apoio do trabalho prático de Redes de Computadores. Os alunos usam o Mininet
para emular um roteador gargalo e medir, no kernel Linux real, a janela de
congestionamento de vários fluxos TCP. Depois testam previsões da geometria da informação
do AIMD: a decomposição pitagórica da divergência de Itakura–Saito em injustiça +
ineficiência, a contração da injustiça por β² a cada ciclo, as leis de escala janela ×
perda e o efeito da sincronização de perdas sobre a justiça entre RTTs.

## Conteúdo

| pasta | o que tem |
|---|---|
| [`enunciado/`](enunciado/) | enunciado em LaTeX (`main.tex`) e em PDF (`enunciado.pdf`) |
| [`ig_starter/`](ig_starter/) | código inicial: topologia haltere, monitor de cwnd, métricas e gráficos — ver o [README](ig_starter/README.md) |

O código da primeira parte (bufferbloat: `bufferbloat.py`, `run.sh`, `monitor.py`, …) e o
manuscrito com os scripts `verify_aimd.py` e `verify_cubic.py` são distribuídos à turma
pelo professor.

## Começo rápido

Na VM do Mininet (Ubuntu 20.04 ou mais novo):

```bash
git clone https://github.com/danielsadoc/trabalho-redes-ig
cd trabalho-redes-ig/ig_starter
sudo apt install iperf3 ethtool
sudo python3 -m pip install mininet matplotlib numpy pandas
sudo python3 dumbbell.py --n 2 --cc reno --rtt-ms 40 --bw 10 --buffer 100 \
     --stagger 15 --duration 120 --qmon --out dados/teste
python3 plot_cwnd.py dados/teste -o teste.png
```

## Compilar o enunciado

```bash
cd enunciado && pdflatex main.tex && pdflatex main.tex
```

Também compila no Overleaf sem ajustes.
