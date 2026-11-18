"""Metricas da geometria da informacao do AIMD e leitura dos dados do dumbbell.py.

Notacao (Secao 3 do enunciado):
    x   vetor de taxas (ou janelas, se os RTTs forem iguais) dos n fluxos
    mu  direcao "justa" (mu = 1 quando todos os RTTs sao iguais)
    c   capacidade (na Parte 4: c = BDP + B, em pacotes)

    U(x) = n log(AM(z)/GM(z)),  z = x/mu                        (injustica)
    I(x) = n (rho - log rho - 1), rho = AM(z) sum(mu) / c        (ineficiencia)
    D_IS(x || x*) = U(x) + I(x),  x* = c mu / sum(mu)            (decomposicao pitagorica)

As funcoes marcadas com TODO fazem parte do trabalho:
    detect_backoffs  -> Parte 4 (pergunta 4.3)
    sync_estimate    -> Parte 6 (pergunta 6.1)
"""

from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------- metricas
def unfairness(x, mu) -> float:
    """U = n log(AM/GM) de z = x/mu. Zero sse x e paralelo a mu; invariante por escala."""
    z = np.asarray(x, float) / np.asarray(mu, float)
    return float(z.size * (np.log(z.mean()) - np.log(z).mean()))


def projected_utilization(x, mu, c: float) -> float:
    """rho = AM(x/mu) sum(mu) / c."""
    z = np.asarray(x, float) / np.asarray(mu, float)
    return float(z.mean() * np.sum(mu) / c)


def inefficiency(x, mu, c: float) -> float:
    """I = n (rho - log rho - 1)."""
    rho = projected_utilization(x, mu, c)
    return float(np.size(x) * (rho - np.log(rho) - 1.0))


def itakura_saito(x, y) -> float:
    """D_IS(x || y) = sum_r [x_r/y_r - log(x_r/y_r) - 1]."""
    r = np.asarray(x, float) / np.asarray(y, float)
    return float(np.sum(r - np.log(r) - 1.0))


def optimum(mu, c: float) -> np.ndarray:
    """x* = c mu / sum(mu)."""
    mu = np.asarray(mu, float)
    return c * mu / mu.sum()


def decompose_series(X: np.ndarray, mu, c: float) -> dict[str, np.ndarray]:
    """Aplica U, I e D_IS(x(t) || x*) a cada linha de X (T x n). Linhas com zeros viram NaN."""
    xs = optimum(mu, c)
    out = {"U": [], "I": [], "D": []}
    for x in X:
        if np.any(~np.isfinite(x)) or np.any(x <= 0):
            for k in out:
                out[k].append(np.nan)
            continue
        out["U"].append(unfairness(x, mu))
        out["I"].append(inefficiency(x, mu, c))
        out["D"].append(itakura_saito(x, xs))
    return {k: np.asarray(v) for k, v in out.items()}


# ----------------------------------------------------------------------------- dados
def load_run(run_dir: str) -> tuple[dict[str, pd.DataFrame], dict]:
    """Le flow*.csv e metadata.json de uma rodada do dumbbell.py."""
    flows = {}
    for path in sorted(glob.glob(os.path.join(run_dir, "flow*.csv")),
                       key=lambda p: int("".join(ch for ch in os.path.basename(p) if ch.isdigit()))):
        df = pd.read_csv(path)
        flows[os.path.basename(path)[:-4]] = df
    meta_path = os.path.join(run_dir, "metadata.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    return flows, meta


def aligned(flows: dict[str, pd.DataFrame], column: str = "cwnd_pkts",
            dt: float = 0.01) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Coloca os fluxos numa grade de tempo comum (passo dt), repetindo a ultima amostra.

    Devolve (t, X, nomes), com X de forma T x n. Antes do inicio de um fluxo, X = NaN.
    """
    names = list(flows)
    t_end = max(df["t_s"].max() for df in flows.values())
    t = np.arange(0.0, t_end, dt)
    X = np.full((t.size, len(names)), np.nan)
    for j, name in enumerate(names):
        df = flows[name].dropna(subset=[column])
        idx = np.searchsorted(df["t_s"].to_numpy(), t, side="right") - 1
        ok = idx >= 0
        X[ok, j] = df[column].to_numpy(float)[idx[ok]]
    return t, X, names


def throughput_mbps(df: pd.DataFrame, t_from: float | None = None, t_to: float | None = None) -> float:
    """Vazao media (Mb/s) a partir de bytes_acked entre t_from e t_to."""
    d = df.dropna(subset=["bytes_acked"])
    if t_from is not None:
        d = d[d["t_s"] >= t_from]
    if t_to is not None:
        d = d[d["t_s"] <= t_to]
    dt = d["t_s"].iloc[-1] - d["t_s"].iloc[0]
    return float(8e-6 * (d["bytes_acked"].iloc[-1] - d["bytes_acked"].iloc[0]) / dt)


# ----------------------------------------------------------------------------- TODO
def detect_backoffs(t, cwnd, ssthresh=None, drop_frac: float = 0.2,
                    timeout_cwnd: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Detecta reducoes de janela de UM fluxo.

    Parametros: t, cwnd (e opcionalmente ssthresh) de um fluxo, na ordem do CSV.
    Regra sugerida: ha uma reducao na amostra k se cwnd[k] < (1 - drop_frac) cwnd[k-1]
    ou se ssthresh mudou. Uma reducao para cwnd <= timeout_cwnd e um timeout.

    Devolve (t_reducoes, t_timeouts), dois arrays de instantes em segundos.
    """
    # TODO (Parte 4, pergunta 4.3)
    raise NotImplementedError


def sync_estimate(backoffs: list[tuple[float, str]], n: int, delta: float) -> tuple[float, float]:
    """Estimador da sincronizacao de perdas, s_hat = (m_bar - 1)/(n - 1).

    backoffs: lista de (t, fluxo) com as reducoes de TODOS os fluxos.
    Agrupe as reducoes em eventos: um evento comeca na primeira reducao ainda nao
    agrupada e inclui as reducoes ate delta segundos depois. m e o numero de fluxos
    DISTINTOS atingidos no evento; m_bar e a media de m.

    Devolve (s_hat, m_bar).
    """
    # TODO (Parte 6, pergunta 6.1)
    raise NotImplementedError
