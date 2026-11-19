#!/usr/bin/env python3
"""Grafico da cwnd de cada fluxo de uma rodada do dumbbell.py (e da fila, se houver).

    python3 plot_cwnd.py dados/p4/reno-n2-B100/rep1 -o p4-cwnd-reno-n2-B100.png
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ig_metrics import load_run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("-o", "--output", default="cwnd.png")
    args = ap.parse_args()

    flows, meta = load_run(args.run_dir)
    qpath = os.path.join(args.run_dir, "queue.csv")
    has_q = os.path.exists(qpath)
    fig, axes = plt.subplots(2 if has_q else 1, 1, figsize=(9, 5.5 if has_q else 3.5),
                             sharex=True, squeeze=False)
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
    if has_q:
        q = pd.read_csv(qpath)
        axes[1, 0].plot(q["t_s"], q["backlog_pkts"], color="0.3", lw=0.8)
        axes[1, 0].set_ylabel("fila (pacotes)")
        axes[1, 0].grid(alpha=0.3)
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
