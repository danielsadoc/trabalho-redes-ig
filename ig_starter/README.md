# ig_starter — código inicial do Trabalho de Redes (geometria da informação do AIMD)

Código para as Partes 2, 4 e 5 do enunciado e para os bônus da Parte 6. Testado no Ubuntu 24.04 com Python 3
(a VM Vagrant com Ubuntu 20.04 pode funcionar, mas não é testada).

## Instalação

```bash
sudo apt install mininet openvswitch-switch openvswitch-testcontroller iperf iperf3 \
     ethtool git python3-numpy python3-pandas python3-matplotlib
sudo modprobe -a sch_netem sch_red  # se falhar: sudo apt install linux-modules-extra-$(uname -r)
sudo modprobe tcp_scalable           # para a Parte 5
```

## Arquivos

| arquivo | o que faz |
|---|---|
| `dumbbell.py` | topologia haltere com `n` emissores; RTT por fluxo; gargalo com taxa `C`, buffer `B`, RED ou perda aleatória; inicia os fluxos escalonados e os monitores; grava CSVs e `metadata.json` |
| `cwnd_monitor.py` | amostra `ss -tin` dentro do host emissor (chamado pelo `dumbbell.py`) |
| `ig_metrics.py` | injustiça `U`, ineficiência `I`, `D_IS`, leitura e alinhamento dos CSVs. **Dois TODOs fazem parte do trabalho**: `detect_backoffs` (Parte 4) e `sync_estimate` (bônus de sincronização) |
| `plot_cwnd.py` | gráfico da cwnd por fluxo (e da fila, se houver `queue.csv`) |
| `run_p4.sh` | varredura de exemplo da Parte 4, com repetições e retomada |
| `simula_aimd.py` | verificação numérica da teoria (Seção 3 do enunciado): identidade pitagórica, contração por β², expoentes binomiais, interpolação por sincronização parcial; `--skip-interpolation` pula a parte mais lenta |
| `simula_cubic.py` | expoente 4/3 do CUBIC sob perda periódica |

## Uso

```bash
# Parte 2: um fluxo Reno, buffer de 100 pacotes; grafico com janela, fila e RTT
sudo python3 dumbbell.py --n 1 --cc reno --rtt-ms 20 --bw 1.5 --buffer 100 \
     --duration 200 --qmon --ping --out dados/p2/q100
python3 plot_cwnd.py dados/p2/q100 -o p2-q100.png

# Parte 4: dois fluxos Reno, RTT 40 ms, 10 Mb/s, buffer de 100 pacotes, inícios a cada 15 s
sudo python3 dumbbell.py --n 2 --cc reno --rtt-ms 40 --bw 10 --buffer 100 \
     --stagger 15 --duration 120 --qmon --out dados/p4/reno-n2-B100/rep1
python3 plot_cwnd.py dados/p4/reno-n2-B100/rep1 -o p4-cwnd-reno-n2-B100.png

# Parte 5: um fluxo Reno com 0,05% de perda aleatória no gargalo (--loss é em PORCENTO)
sudo python3 dumbbell.py --n 1 --cc reno --rtt-ms 100 --bw 50 --buffer 2000 \
     --loss 0.05 --duration 300 --out dados/p5/reno-p5e-4/rep1

# Bônus de sincronização: três fluxos Reno com RTTs 20/40/60 ms, RED no gargalo
sudo python3 dumbbell.py --n 3 --cc reno --rtt-ms 20,40,60 --bw 10 --buffer 100 \
     --red --duration 200 --out dados/p6/red-B100/rep1

sudo python3 dumbbell.py -h          # todas as opções
```

Cada rodada grava, em `--out`:

* `flow<i>.csv` — `t_s, flow_id, cc, cwnd_pkts, ssthresh_pkts, srtt_ms, bytes_acked`
  (tempo comum a todos os fluxos; `flow_id` é a porta de origem `50000+i`);
* `iperf_flow<i>.json` — saída do iperf3;
* `queue.csv` (com `--qmon`) — ocupação e descartes da fila do gargalo;
* `ping.txt` (com `--ping`) — pings de h1 para r a 10 Hz;
* `metadata.json` — parâmetros, comandos `tc` aplicados, estado final da fila, RTT mínimo medido
  por ping antes dos fluxos, versões do kernel/Mininet/iperf3, carga da CPU, commit.

### Como a rede é montada

* O RTT de propagação do fluxo *i* é aplicado com `netem delay` na saída do próprio
  emissor (`hi → s1`). Isso também desliga o pacote do socket ao entrar no netem; sem
  isso, em kernels recentes o *TCP Small Queues* limita cada fluxo a poucos pacotes na
  fila do gargalo e o buffer nunca enche, o que não acontece com um roteador de verdade.
* O gargalo é a saída `s1 → s2`: `htb rate C` com uma fila folha `handle 20:` que é
  `pfifo limit B` (drop-tail), `red` (`--red`, limiares em `--red-min/--red-max` × B) ou
  `netem loss p% limit B` (`--loss`).
* Offloads (TSO/GSO/GRO) são desligados e `tcp_no_metrics_save=1` em todos os hosts.
* Se o Open vSwitch não estiver disponível, use `--switch lxbr`.

## Cuidados

* Confira em `metadata.json` que `loadavg_fim` não ficou perto do número de CPUs da VM:
  se a CPU saturar, o Mininet deixa de ser fiel.
* A perda do `netem` usa o gerador aleatório do kernel, sem semente: a variabilidade entre
  rodadas é real, por isso as repetições.
* A cwnd é inteira: para `n=2`, a injustiça `U` tem um piso de ruído da ordem de
  `1/(2w)^2`. Não interprete razões de ciclo abaixo disso.
