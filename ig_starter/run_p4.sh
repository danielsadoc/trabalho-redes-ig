#!/bin/bash
# Varredura de exemplo da Parte 4: algoritmo x numero de fluxos x buffer x repeticao.
# Uso: sudo ./run_p4.sh   (ajuste REPS e as listas abaixo; cada rodada leva ~3 min)
set -e
cd "$(dirname "$0")"
REPS=${REPS:-5}
RTT=40        # ms, igual para todos os fluxos
BW=10         # Mb/s
STAGGER=15    # s entre os inicios dos fluxos
DUR=120       # s apos o inicio do ultimo fluxo

for cc in reno cubic; do
  for n in 2 3 4; do
    for B in 20 100; do
      for rep in $(seq 1 "$REPS"); do
        out="dados/p4/${cc}-n${n}-B${B}/rep${rep}"
        [ -f "$out/metadata.json" ] && continue   # retoma de onde parou
        python3 dumbbell.py --n "$n" --cc "$cc" --rtt-ms "$RTT" --bw "$BW" \
                --buffer "$B" --stagger "$STAGGER" --duration "$DUR" --qmon --out "$out"
        mn -c >/dev/null 2>&1 || true
      done
    done
  done
done
python3 plot_cwnd.py dados/p4/reno-n2-B100/rep1 -o p4-cwnd-reno-n2-B100.png
