#!/usr/bin/env python3
"""Amostra a janela de congestionamento de UM fluxo TCP com `ss -tin`.

Roda DENTRO do host emissor do Mininet (o dumbbell.py chama via h.popen), porque
cada host tem seu proprio namespace de rede e o `ss` so enxerga os sockets dele.

Saida: CSV com as colunas
    t_s, flow_id, cc, cwnd_pkts, ssthresh_pkts, srtt_ms, bytes_acked

  t_s           segundos desde --t0 (relogio de parede; todos os hosts do Mininet
                compartilham o mesmo relogio, entao os fluxos ficam alinhados)
  flow_id       porta de origem do fluxo (--sport)
  cc            algoritmo de controle de congestionamento reportado pelo kernel
  cwnd_pkts     janela de congestionamento, em segmentos
  ssthresh_pkts limiar de slow start, em segmentos (vazio enquanto nao definido)
  srtt_ms       RTT suavizado do kernel
  bytes_acked   bytes confirmados ate agora (derive para obter a vazao)

Exemplo (dentro do host):
    python3 cwnd_monitor.py --dst 10.0.0.3 --sport 50001 --out f1.csv --duration 60
"""

from __future__ import annotations

import argparse
import csv
import re
import signal
import subprocess
import sys
import time

# tokens sem ":" que aparecem na linha de detalhes do ss e NAO sao o nome do algoritmo
_NOT_CC = {"ts", "sack", "ecn", "ecnseen", "fastopen", "noecn", "app_limited", "ce", "ecnseen"}
_RE_KV = re.compile(r"(\w+):(\S+)")


def parse_ss(output: str, sport: int) -> dict | None:
    """Extrai os campos do socket cuja porta local e `sport`. Devolve None se nao achar."""
    lines = output.splitlines()
    for k, line in enumerate(lines):
        if line.startswith(("State", "Recv-Q", "Netid")) or not line.strip() or line[0].isspace():
            continue
        # colunas: [State] Recv-Q Send-Q Local:Port Peer:Port [Process]
        # (com filtro de estado, o ss omite a coluna State)
        cols = line.split()
        if not any(tok.endswith(f":{sport}") for tok in cols[:5]):
            continue
        if k + 1 >= len(lines):
            return None
        info = lines[k + 1].split()
        kv = dict(_RE_KV.findall(lines[k + 1]))
        cc = next((tok for tok in info if ":" not in tok and tok not in _NOT_CC), "")
        rtt = kv.get("rtt", "")
        return {
            "cc": cc,
            "cwnd_pkts": kv.get("cwnd", ""),
            "ssthresh_pkts": kv.get("ssthresh", ""),
            "srtt_ms": rtt.split("/")[0] if rtt else "",
            "bytes_acked": kv.get("bytes_acked", "0"),
        }
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dst", required=True, help="IP do receptor")
    ap.add_argument("--sport", type=int, required=True, help="porta de origem do fluxo (iperf3 --cport)")
    ap.add_argument("--out", required=True, help="arquivo CSV de saida")
    ap.add_argument("--interval", type=float, default=0.01, help="periodo de amostragem em s (padrao 0.01)")
    ap.add_argument("--duration", type=float, default=60.0, help="tempo maximo de coleta em s")
    ap.add_argument("--t0", type=float, default=None, help="instante de referencia (epoch); padrao: agora")
    args = ap.parse_args()

    t0 = args.t0 if args.t0 is not None else time.time()
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    cmd = ["ss", "-tin", "state", "established", "dst", args.dst]
    fields = ["t_s", "flow_id", "cc", "cwnd_pkts", "ssthresh_pkts", "srtt_ms", "bytes_acked"]
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        next_tick = time.time()
        deadline = time.time() + args.duration
        n = 0
        while not stop and time.time() < deadline:
            now = time.time()
            out = subprocess.run(cmd, capture_output=True, text=True).stdout
            row = parse_ss(out, args.sport)
            if row is not None:
                row.update(t_s=f"{now - t0:.4f}", flow_id=args.sport)
                writer.writerow(row)
                n += 1
                if n % 100 == 0:
                    fh.flush()
            next_tick += args.interval
            delay = next_tick - time.time()
            if delay > 0:
                time.sleep(delay)
            else:  # atrasou (CPU ocupada): realinha sem acumular atraso
                next_tick = time.time()
    print(f"cwnd_monitor: {n} amostras gravadas em {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
