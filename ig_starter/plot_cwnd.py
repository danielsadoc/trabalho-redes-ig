#!/usr/bin/env python3
"""Grafico da cwnd de cada fluxo de uma rodada do dumbbell.py, mais a fila do gargalo
(se a rodada usou --qmon) e o RTT do ping (se usou --ping), um painel para cada.

    python3 plot_cwnd.py dados/p4/reno-n2-B100/rep1 -o p4-cwnd-reno-n2-B100.png
    python3 plot_cwnd.py dados/p2/q100 -o p2-q100.png      # Parte 2: cwnd, fila e RTT
"""

import argparse
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ig_metrics import load_run  # noqa: E402

PING_RE = re.compile(r"^\[(\d+\.\d+)\].*time=([\d.]+) ms")


def load_ping(path: str, t0: float) -> pd.DataFrame:
    """Le a saida de `ping -D` e devolve t_s (desde t0) e rtt_ms."""
    rows = []
    with open(path) as fh:
        for line in fh:
            m = PING_RE.match(line)
            if m:
                rows.append((float(m.group(1)) - t0, float(m.group(2))))
    return pd.DataFrame(rows, columns=["t_s", "rtt_ms"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("-o", "--output", default="cwnd.png")
    args = ap.parse_args()

    flows, meta = load_run(args.run_dir)
    qpath = os.path.join(args.run_dir, "queue.csv")
    ppath = os.path.join(args.run_dir, "ping.txt")
    has_q = os.path.exists(qpath)
    has_p = os.path.exists(ppath) and "inicio_epoch" in meta
    npan = 1 + has_q + has_p
    fig, axes = plt.subplots(npan, 1, figsize=(9, 2.2 + 2.0 * npan), sharex=True, squeeze=False)
    ax = axes[0, 0]
    ccs = meta.get("cc_por_fluxo", [])
    rtts = meta.get("rtt_prop_ms_por_fluxo", [])
    for k, (name, df) in enumerate(flows.items()):
        label = name
        if k < len(ccs):
            label += f" ({ccs[k]}, {rtts[k]:g} ms)"
        ax.plot(df["t_s"], df["cwnd_pkts"], lw=0.9, label=label)
    ax.set_ylabel("cwnd (pacotes)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    k = 1
    if has_q:
        q = pd.read_csv(qpath)
        axes[k, 0].plot(q["t_s"], q["backlog_pkts"], color="0.3", lw=0.8)
        axes[k, 0].set_ylabel("fila (pacotes)")
        axes[k, 0].grid(alpha=0.3)
        k += 1
    if has_p:
        pg = load_ping(ppath, float(meta["inicio_epoch"]))
        axes[k, 0].plot(pg["t_s"], pg["rtt_ms"], color="tab:red", lw=0.8)
        axes[k, 0].set_ylabel("RTT do ping (ms)")
        axes[k, 0].grid(alpha=0.3)
        if len(pg):
            print(f"RTT do ping: media {pg['rtt_ms'].mean():.1f} ms, "
                  f"desvio {pg['rtt_ms'].std():.1f} ms ({len(pg)} amostras)")
    axes[-1, 0].set_xlabel("tempo (s)")
    a = meta.get("args", {})
    if a:
        fig.suptitle(f"C={a.get('bw')} Mb/s, B={a.get('buffer')} pacotes"
                     + (f", {a.get('qdisc')}" if a.get("qdisc", "pfifo") != "pfifo" else "")
                     + (", RED" if a.get("red") and not a.get("qdisc") else "")
                     + (", ECN" if a.get("ecn") else "")
                     + (f", perda={a.get('loss')}%" if a.get("loss") else ""), fontsize=10)
    fig.tight_layout()
    fig.savefig(args.output, dpi=150)
    print(f"gravado {args.output}")


if __name__ == "__main__":
    main()
