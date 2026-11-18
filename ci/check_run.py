#!/usr/bin/env python3
"""Verifica uma rodada do dumbbell.py (usado pelo GitHub Actions).

    python3 ci/check_run.py DIR [--rtt-ms 20,40,60] [--expect red|loss] [--min-samples 500]
"""
import argparse
import csv
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--rtt-ms", default=None, help="RTTs de propagacao esperados por fluxo")
    ap.add_argument("--expect", choices=["red", "loss"], default=None)
    ap.add_argument("--min-samples", type=int, default=500)
    ap.add_argument("--min-backoffs", type=int, default=0,
                    help="minimo de reducoes de janela por fluxo (quedas de cwnd > 20%%)")
    a = ap.parse_args()

    erros = []
    meta = json.load(open(os.path.join(a.run_dir, "metadata.json")))
    n = meta["args"]["n"]
    print(f"== {a.run_dir}: n={n}, kernel {meta['kernel']}")
    for i in range(1, n + 1):
        rows = list(csv.DictReader(open(os.path.join(a.run_dir, f"flow{i}.csv"))))
        cwnd = [float(r["cwnd_pkts"]) for r in rows if r["cwnd_pkts"]]
        cc = {r["cc"] for r in rows}
        backoffs = sum(1 for a_, b_ in zip(cwnd, cwnd[1:]) if b_ < 0.8 * a_)
        print(f"   flow{i}: {len(rows)} amostras, cc={cc}, cwnd min/max={min(cwnd, default=0):.0f}/"
              f"{max(cwnd, default=0):.0f}, reducoes de janela={backoffs}")
        if backoffs < a.min_backoffs:
            erros.append(f"flow{i}: so {backoffs} reducoes de janela (esperava >= {a.min_backoffs})")
        if len(rows) < a.min_samples:
            erros.append(f"flow{i}: so {len(rows)} amostras")
        it = json.load(open(os.path.join(a.run_dir, f"iperf_flow{i}.json")))
        if "error" in it:
            erros.append(f"iperf3 flow{i}: {it['error']}")
        else:
            print(f"   flow{i}: iperf3 {it['end']['sum_received']['bits_per_second'] / 1e6:.2f} Mb/s")
    qpath = os.path.join(a.run_dir, "queue.csv")
    if os.path.exists(qpath):
        q = list(csv.DictReader(open(qpath)))
        if q:
            backlog = [int(r["backlog_pkts"]) for r in q]
            print(f"   fila: ocupacao media {sum(backlog) / len(backlog):.1f}, max {max(backlog)} pacotes; "
                  f"descartes {q[-1]['dropped']}")
    medido = meta["rtt_medido_ping_ms"]
    print(f"   RTT medido por ping: {medido}")
    if a.rtt_ms:
        alvo = [float(x) for x in a.rtt_ms.split(",")]
        alvo = alvo * n if len(alvo) == 1 else alvo
        for i, t in enumerate(alvo, start=1):
            m = medido.get(f"h{i}")
            if m is None or not (0.9 * t <= m <= 1.1 * t + 2.0):
                erros.append(f"h{i}: RTT medido {m} ms, esperado ~{t} ms")
    q = meta["qdisc_gargalo"]
    print("   " + q.replace("\n", "\n   ").rstrip())
    if a.expect == "red" and "qdisc red 20:" not in q:
        erros.append("RED nao esta instalado no gargalo")
    if a.expect == "loss" and "loss" not in q:
        erros.append("netem loss nao esta instalado no gargalo")
    for e in erros:
        print(f"ERRO: {e}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
