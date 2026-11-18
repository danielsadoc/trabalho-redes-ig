#!/bin/bash
# Experimentos de referencia do enunciado, em grupos (usado pelo GitHub Actions).
# Uso (em ig_starter/): ../ci/experimentos.sh p2p4|p5reno|p5cubic|p5scalable|p6
set -e
run() { out=$1; shift; sudo mn -c >/dev/null 2>&1 || true
        sudo python3 dumbbell.py "$@" --out dados/$out
        python3 plot_cwnd.py dados/$out -o dados/$out/cwnd.png; }
p5() { for p in 0.02 0.05 0.1 0.2 0.5 1 2; do
         run p5/$1-p$p --n 1 --cc $1 --rtt-ms 100 --bw 50 --buffer 2000 --loss $p --duration 90
       done; }
case "$1" in
  p2p4)
    run p2/q100 --n 1 --cc reno --rtt-ms 20 --bw 1.5 --buffer 100 --duration 60 --qmon --ping
    run p2/q20  --n 1 --cc reno --rtt-ms 20 --bw 1.5 --buffer 20  --duration 60 --qmon --ping
    run p4/reno-n2-B100  --n 2 --cc reno  --rtt-ms 40 --bw 10 --buffer 100 --stagger 15 --duration 120 --qmon
    run p4/cubic-n2-B100 --n 2 --cc cubic --rtt-ms 40 --bw 10 --buffer 100 --stagger 15 --duration 120 --qmon
    run p4/reno-n3-B20   --n 3 --cc reno  --rtt-ms 40 --bw 10 --buffer 20  --stagger 15 --duration 120 --qmon ;;
  p5reno) p5 reno ;;
  p5cubic) p5 cubic ;;
  p5scalable) p5 scalable ;;
  p6)
    run p6/droptail-B100 --n 3 --cc reno --rtt-ms 20,40,60 --bw 10 --buffer 100 --duration 120 --qmon
    run p6/red-B100      --n 3 --cc reno --rtt-ms 20,40,60 --bw 10 --buffer 100 --red --duration 120 --qmon
    run p6/droptail-B20  --n 3 --cc reno --rtt-ms 20,40,60 --bw 10 --buffer 20 --duration 120 --qmon ;;
  *) echo "grupo desconhecido: $1"; exit 1 ;;
esac
