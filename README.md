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
| [`ig_starter/`](ig_starter/) | código inicial: topologia haltere, monitor de cwnd, métricas, gráficos e verificações numéricas da teoria — ver o [README](ig_starter/README.md) |

O enunciado é autocontido: a teoria está na Seção 3 e as derivações no Apêndice C. O
código da primeira parte (bufferbloat: `bufferbloat.py`, `run.sh`, `monitor.py`, …) é o
do projeto de bufferbloat da disciplina, distribuído à turma pelo professor.

## Começo rápido

No Ubuntu 24.04 (testado; a VM Vagrant com Ubuntu 20.04 pode funcionar, mas não é testada):

```bash
sudo apt install mininet openvswitch-switch openvswitch-testcontroller iperf iperf3 \
     ethtool git python3-numpy python3-pandas python3-matplotlib
git clone https://github.com/danielsadoc/trabalho-redes-ig
cd trabalho-redes-ig/ig_starter
sudo python3 dumbbell.py --n 2 --cc reno --rtt-ms 40 --bw 10 --buffer 100 \
     --stagger 15 --duration 120 --qmon --out dados/teste
python3 plot_cwnd.py dados/teste -o teste.png
```

## Testes automáticos

* **Mininet (dumbbell.py)** roda a cada mudança no código: atraso por fluxo, RED, perda
  aleatória e um cenário da Parte 4, com verificações de RTT, perdas e qdisc.
* **Experimentos de referência** (disparo manual na aba *Actions*) roda versões curtas
  das Partes 2, 4, 5 e 6 e guarda os dados como artefatos.

## Compilar o enunciado

```bash
cd enunciado && pdflatex main.tex && pdflatex main.tex
```

Também compila no Overleaf sem ajustes.
