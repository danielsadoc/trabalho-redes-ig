#!/usr/bin/env python3
"""Topologia haltere (dumbbell) para as Partes 2, 4, 5 e 6 do trabalho.

    h1 --\\
    h2 ---- s1 ==== gargalo (C, B) ==== s2 ---- r
    hn --/

* n emissores h1..hn, um receptor r.
* O RTT de propagacao do fluxo i e aplicado com netem na saida do proprio emissor
  (hi -> s1). O netem "solta" o pacote do socket ao enfileira-lo; sem isso, em kernels
  recentes o TCP Small Queues limita cada fluxo a poucos pacotes na fila do gargalo,
  que nunca enche (o roteador de verdade nao esta no mesmo kernel que o emissor).
* O gargalo e a saida s1 -> s2: HTB com taxa C e, abaixo dele, uma fila de B pacotes
  (drop-tail = pfifo; ou RED com --red; ou netem com perda aleatoria com --loss).
* Cada emissor abre UM fluxo iperf3 para r, com o algoritmo escolhido por fluxo
  (iperf3 -C), comecando em t = i * stagger. Todos terminam juntos.
* Em cada emissor roda o cwnd_monitor.py; opcionalmente, um monitor da fila do
  gargalo (--qmon) e um trem de pings h1 -> r a 10 Hz (--ping).

Saida em --out:
    flow1.csv ... flown.csv   amostras de cwnd (ver cwnd_monitor.py)
    iperf_flowi.json          saida do iperf3 de cada fluxo
    queue.csv                 (--qmon) t_s, backlog_pkts, backlog_bytes, dropped
    ping.txt                  (--ping) saida do ping
    metadata.json             parametros, comandos tc, versoes, RTTs medidos

Exemplos:
    sudo python3 dumbbell.py --n 2 --cc reno --rtt-ms 40 --bw 10 --buffer 100 \\
         --stagger 15 --duration 150 --out dados/p4/reno-n2-B100/rep1
    sudo python3 dumbbell.py --n 3 --cc reno --rtt-ms 20,40,60 --bw 10 --buffer 50 \\
         --red --duration 200 --out dados/p6/red/rep1
    sudo python3 dumbbell.py --n 1 --cc cubic --rtt-ms 100 --bw 50 --buffer 2000 \\
         --loss 0.05 --duration 300 --out dados/p5/cubic-p5e-4/rep1
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time

from mininet.clean import cleanup
from mininet.log import setLogLevel
from mininet.net import VERSION as MININET_VERSION, Mininet
from mininet.node import OVSBridge
from mininet.nodelib import LinuxBridge
from mininet.topo import Topo

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PORT = 5200   # iperf3 do fluxo i escuta em BASE_PORT + i
BASE_CPORT = 50000  # porta de origem do fluxo i = BASE_CPORT + i (identifica o fluxo)
TCP_MEM = "4096 8388608 33554432"  # tcp_rmem/tcp_wmem em todos os hosts (min padrao max)


class Dumbbell(Topo):
    def build(self, n: int = 2):
        s1 = self.addSwitch("s1")
        s2 = self.addSwitch("s2")
        r = self.addHost("r")
        for i in range(1, n + 1):
            self.addLink(self.addHost(f"h{i}"), s1)
        self.addLink(s1, s2)  # gargalo
        self.addLink(s2, r)


def lista(valor: str, n: int, tipo=str) -> list:
    """'a,b,c' -> [a,b,c]; 'a' -> [a]*n."""
    itens = [tipo(v) for v in str(valor).split(",")]
    if len(itens) == 1:
        itens = itens * n
    if len(itens) != n:
        sys.exit(f"esperava 1 ou {n} valores em '{valor}'")
    return itens


def sh(cmd: str, log: list) -> str:
    """Roda um comando no namespace raiz (onde estao as interfaces dos switches)."""
    log.append(cmd)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"falhou: {cmd}\n{res.stderr}")
    return res.stdout


def configura_gargalo(intf: str, args, log: list) -> None:
    """HTB com taxa C e fila de B pacotes na saida s1 -> s2."""
    sh(f"tc qdisc del dev {intf} root 2>/dev/null || true", log)
    sh(f"tc qdisc add dev {intf} root handle 1: htb default 10", log)
    sh(f"tc class add dev {intf} parent 1: classid 1:10 htb rate {args.bw}mbit", log)
    if args.loss > 0:
        # netem como fila FIFO de B pacotes com perda iid por pacote (em porcento)
        leaf = f"netem loss {args.loss}% limit {args.buffer}"
    elif args.red:
        mtu = 1500
        minth = int(args.red_min * args.buffer * mtu)
        maxth = int(args.red_max * args.buffer * mtu)
        burst = max(2, int((2 * minth + maxth) / (3 * mtu)))
        leaf = (f"red limit {args.buffer * mtu * 4} min {minth} max {maxth} avpkt {mtu} "
                f"burst {burst} bandwidth {args.bw}mbit probability {args.red_prob}")
    else:
        leaf = f"pfifo limit {args.buffer}"
    sh(f"tc qdisc add dev {intf} parent 1:10 handle 20: {leaf}", log)


def configura_atraso(host, rtt_ms: float, log: list) -> None:
    """RTT de propagacao inteiro aplicado na saida do emissor (host -> s1).

    Mesmo com rtt_ms = 0 instalamos um netem com atraso minimo (10 us): o netem desliga
    o pacote do socket (skb_orphan_partial) e o TCP Small Queues para de contar os
    pacotes que estao na fila do gargalo como se estivessem na placa do emissor.
    """
    intf = host.defaultIntf().name
    atraso = f"{rtt_ms}ms" if rtt_ms > 0 else "10us"
    for cmd in (f"tc qdisc del dev {intf} root 2>/dev/null || true",
                f"tc qdisc add dev {intf} root netem delay {atraso} limit 100000"):
        log.append(f"[{host.name}] {cmd}")
        out = host.cmd(cmd + " ; echo rc=$?")
        if "del dev" not in cmd and not out.strip().endswith("rc=0"):
            sys.exit(f"falhou em {host.name}: {cmd}\n{out}")


def monitor_fila(intf: str, t0: float, path: str, interval: float, stop: threading.Event) -> None:
    pat_backlog = re.compile(r"backlog (\d+)b (\d+)p")
    pat_drop = re.compile(r"dropped (\d+)")
    with open(path, "w") as fh:
        fh.write("t_s,backlog_pkts,backlog_bytes,dropped\n")
        while not stop.is_set():
            now = time.time()
            out = subprocess.run(["tc", "-s", "qdisc", "show", "dev", intf],
                                 capture_output=True, text=True).stdout
            # um bloco por qdisc; o que interessa e a fila folha (handle 20:)
            blocos = ["qdisc " + b for b in out.split("qdisc ") if b.strip()]
            bloco = next((b for b in blocos if b.split("\n")[0].split()[2:3] == ["20:"]), "")
            b = pat_backlog.search(bloco)
            d = pat_drop.search(bloco)
            if b and d:
                fh.write(f"{now - t0:.4f},{b.group(2)},{b.group(1)},{d.group(1)}\n")
            time.sleep(max(0.0, interval - (time.time() - now)))


def versao(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        return "desconhecida"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=2, help="numero de emissores/fluxos")
    ap.add_argument("--cc", default="reno", help="algoritmo por fluxo: 'reno' ou 'reno,cubic,...'")
    ap.add_argument("--rtt-ms", default="40", help="RTT de propagacao por fluxo: '40' ou '20,40,60'")
    ap.add_argument("--bw", type=float, default=10.0, help="capacidade do gargalo em Mb/s")
    ap.add_argument("--buffer", type=int, default=100, help="buffer do gargalo em pacotes")
    ap.add_argument("--red", action="store_true", help="usar RED no gargalo em vez de drop-tail")
    ap.add_argument("--red-min", type=float, default=0.2, help="limiar minimo do RED (fracao do buffer)")
    ap.add_argument("--red-max", type=float, default=0.6, help="limiar maximo do RED (fracao do buffer)")
    ap.add_argument("--red-prob", type=float, default=0.1, help="probabilidade maxima de descarte do RED")
    ap.add_argument("--loss", type=float, default=0.0, help="perda aleatoria no gargalo, em PORCENTO")
    ap.add_argument("--stagger", type=float, default=0.0, help="intervalo entre inicios dos fluxos (s)")
    ap.add_argument("--duration", type=float, default=60.0, help="duracao apos o inicio do ultimo fluxo (s)")
    ap.add_argument("--interval", type=float, default=0.01, help="periodo de amostragem da cwnd (s)")
    ap.add_argument("--qmon", action="store_true", help="registrar a ocupacao da fila do gargalo")
    ap.add_argument("--ping", action="store_true", help="trem de pings h1 -> r a 10 Hz")
    ap.add_argument("--switch", choices=["ovsbr", "lxbr"], default="ovsbr",
                    help="tipo de switch (lxbr se o Open vSwitch nao estiver disponivel)")
    ap.add_argument("--out", required=True, help="diretorio de saida")
    ap.add_argument("--cli", action="store_true", help="abrir a CLI do Mininet antes de sair")
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("rode com sudo")
    n = args.n
    ccs = lista(args.cc, n)
    rtts = lista(args.rtt_ms, n, float)
    os.makedirs(args.out, exist_ok=True)
    tc_log: list[str] = []

    setLogLevel("warning")
    cleanup()
    for cc in set(ccs):
        subprocess.run(["modprobe", f"tcp_{cc}"], capture_output=True)

    switch = OVSBridge if args.switch == "ovsbr" else LinuxBridge
    net = Mininet(topo=Dumbbell(n=n), switch=switch, controller=None, autoSetMacs=True,
                  autoStaticArp=True)  # sem ARP durante o experimento
    net.start()
    try:
        s1, s2, r = net.get("s1"), net.get("s2"), net.get("r")
        hosts = [net.get(f"h{i}") for i in range(1, n + 1)]

        # offloads distorcem cwnd e fila; metricas de conexoes anteriores tambem
        for node in hosts + [r]:
            for intf in node.intfList():
                if intf.name != "lo":
                    node.cmd(f"ethtool -K {intf.name} tso off gso off gro off 2>/dev/null")
            node.cmd("sysctl -qw net.ipv4.tcp_no_metrics_save=1")
            # buffers de socket grandes desde o inicio: com o padrao (128 kB) a janela do
            # receptor limita a cwnd a ~44 pacotes e o buffer do gargalo nunca enche
            node.cmd(f"sysctl -qw net.ipv4.tcp_rmem='{TCP_MEM}' net.ipv4.tcp_wmem='{TCP_MEM}'")
        for sw in (s1, s2):
            for intf in sw.intfList():
                if intf.name != "lo":
                    subprocess.run(f"ethtool -K {intf.name} tso off gso off gro off", shell=True,
                                   capture_output=True)

        estado_hosts = {
            "tcp_rmem_receptor": r.cmd("sysctl -n net.ipv4.tcp_rmem").strip(),
            "tcp_wmem_emissor": hosts[0].cmd("sysctl -n net.ipv4.tcp_wmem").strip(),
            "qdisc_emissor": hosts[0].cmd(f"tc qdisc show dev {hosts[0].defaultIntf()}").strip(),
            "cc_padrao": hosts[0].cmd("sysctl -n net.ipv4.tcp_congestion_control").strip(),
        }
        gargalo = s1.connectionsTo(s2)[0][0].name
        configura_gargalo(gargalo, args, tc_log)
        for h, rtt in zip(hosts, rtts):
            configura_atraso(h, rtt, tc_log)

        # RTT minimo medido antes de ligar os fluxos (o minimo descarta a resolucao ARP)
        rtt_medido = {}
        for h in hosts:
            out = h.cmd(f"ping -c 10 -i 0.2 -q {r.IP()}")
            m = re.search(r"= ([\d.]+)/[\d.]+/", out)
            rtt_medido[h.name] = float(m.group(1)) if m else None

        # servidores iperf3 (um por fluxo)
        servers = [r.popen(["iperf3", "-s", "-1", "-p", str(BASE_PORT + i)])
                   for i in range(1, n + 1)]
        time.sleep(1.0)

        total = (n - 1) * args.stagger + args.duration
        t0 = time.time() + 1.0
        monitors = []
        for i, h in enumerate(hosts, start=1):
            monitors.append(h.popen([
                sys.executable, os.path.join(HERE, "cwnd_monitor.py"),
                "--dst", r.IP(), "--sport", str(BASE_CPORT + i),
                "--out", os.path.join(args.out, f"flow{i}.csv"),
                "--interval", str(args.interval), "--duration", str(total + 3),
                "--t0", f"{t0:.6f}"]))

        stop = threading.Event()
        qthread = None
        if args.qmon:
            qthread = threading.Thread(target=monitor_fila, daemon=True,
                                       args=(gargalo, t0, os.path.join(args.out, "queue.csv"),
                                             args.interval, stop))
            qthread.start()
        ping = None
        if args.ping:
            ping = hosts[0].popen(f"ping -i 0.1 -D {r.IP()} > {os.path.join(args.out, 'ping.txt')}",
                                  shell=True)

        clients = []
        for i, (h, cc) in enumerate(zip(hosts, ccs), start=1):
            start = t0 + (i - 1) * args.stagger
            time.sleep(max(0.0, start - time.time()))
            dur = max(1, round(t0 + total - time.time()))
            log = open(os.path.join(args.out, f"iperf_flow{i}.json"), "w")
            clients.append(h.popen(["iperf3", "-c", r.IP(), "-p", str(BASE_PORT + i),
                                    "--cport", str(BASE_CPORT + i), "-C", cc,
                                    "-t", str(dur), "-i", "1", "-J"], stdout=log))
            print(f"[{time.time() - t0:6.1f}s] fluxo {i} ({cc}, RTT {rtts[i-1]} ms) iniciado")

        for c in clients:
            c.wait()
        time.sleep(1.0)
        for p in monitors + ([ping] if ping else []):
            p.terminate()
        for p in monitors:
            p.wait()
        stop.set()
        if qthread:
            qthread.join(timeout=2)
        for s in servers:
            s.terminate()

        meta = {
            "args": vars(args),
            "cc_por_fluxo": ccs,
            "rtt_prop_ms_por_fluxo": rtts,
            "rtt_medido_ping_ms": rtt_medido,
            "flow_id_por_fluxo": {f"flow{i}": BASE_CPORT + i for i in range(1, n + 1)},
            "interface_gargalo": gargalo,
            "comandos_tc": tc_log,
            "tcp_rmem_wmem": TCP_MEM,
            "estado_hosts": estado_hosts,
            "qdisc_gargalo": subprocess.run(["tc", "-s", "qdisc", "show", "dev", gargalo],
                                            capture_output=True, text=True).stdout,
            "kernel": platform.release(),
            "mininet": MININET_VERSION,
            "iperf3": versao(["iperf3", "--version"]),
            "python": platform.python_version(),
            "loadavg_fim": os.getloadavg(),
            "inicio_epoch": t0,
            "data": dt.datetime.now().isoformat(timespec="seconds"),
            "commit": versao(["git", "-C", HERE, "rev-parse", "HEAD"]),
        }
        with open(os.path.join(args.out, "metadata.json"), "w") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
        # os arquivos foram criados como root; devolve ao usuario que chamou o sudo
        if os.environ.get("SUDO_UID"):
            subprocess.run(["chown", "-R", f"{os.environ['SUDO_UID']}:{os.environ.get('SUDO_GID', '')}",
                            args.out], capture_output=True)
        print(f"ok: resultados em {args.out}")
        if args.cli:
            from mininet.cli import CLI
            CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
