#!/usr/bin/env python3
"""Confere se o ambiente roda o que o bufferbloat.py original usa (Parte 2):
TCLink com max_queue_size, controlador padrao do Mininet, iperf (v2) e a leitura da
fila com `tc -s qdisc` como no monitor.py. Nao e a solucao da Parte 2.

No Ubuntu 24.04 o CPULimitedHost do bufferbloat.py original falha ("cgroups not mounted
on /sys/fs/cgroup": ele depende de cgroups v1). O enunciado manda trocar por Host, que e
o que este teste usa.
"""
import re
import subprocess
import sys
import time

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import Host
from mininet.topo import Topo


class T(Topo):
    def build(self):
        a, b = self.addHost("a"), self.addHost("b")
        s = self.addSwitch("s0")
        self.addLink(a, s, bw=100, delay="2ms")
        self.addLink(s, b, bw=2, delay="2ms", max_queue_size=50)


net = Mininet(topo=T(), host=Host, link=TCLink)
net.start()
erros = []
try:
    a, b = net.get("a", "b")
    if net.pingAll() > 0:
        erros.append("pingAll perdeu pacotes")
    b.popen("iperf -s -w 16m")
    time.sleep(1)
    cli = a.popen(f"iperf -c {b.IP()} -t 15 -Z reno")
    pat = re.compile(rb"backlog\s[^\s]+\s([\d]+)p")  # mesma regex do monitor.py
    maxq = 0
    for _ in range(140):
        out = subprocess.run("tc -s qdisc show dev s0-eth2", shell=True, capture_output=True).stdout
        m = pat.findall(out)
        if len(m) > 1:
            maxq = max(maxq, int(m[1]))
        time.sleep(0.1)
    cli.wait()
    print(f"fila maxima lida como no monitor.py: {maxq} pacotes")
    if maxq < 25:
        erros.append(f"a fila do gargalo nao encheu (max {maxq} de 50)")
finally:
    net.stop()
for e in erros:
    print("ERRO:", e)
sys.exit(1 if erros else 0)
