"""Verificações numéricas dos resultados sobre AIMD e divergência de Itakura--Saito.

Itens (Secao 3 e Apendice C do enunciado):
  1. identidade pitagórica   D_IS(x || x*) = injustiça + ineficiência
  2. transiente da utilização projetada  rho_{m+1} - 1 = beta (rho_m - 1)
  3. contração transversal   injustiça monótona, razão por ciclo -> beta^2
  4. expoentes binomiais     alpha = k + l + 1 sob perda i.i.d. por pacote
  5. interpolação            alpha_eff = k + l + (1-s)/(s n + 1 - s)

Convenção: ``beta`` é a fração RETIDA da janela após a perda (x <- beta x).

Por padrão os expoentes do item 4 usam a mesma semente para todas as probabilidades
de perda (números aleatórios comuns), o que cancela parte do ruído na inclinação do
ajuste log-log. Use ``--independent-seeds`` para sementes distintas por ponto.
"""

from __future__ import annotations

import argparse

import numpy as np


# --------------------------------------------------------------------------- medidas
def unfairness(x: np.ndarray, mu: np.ndarray) -> float:
    """Calcula n log(AM/GM) para z = x/mu. Invariante a escala; zero <=> x paralelo a mu."""
    z = np.asarray(x, dtype=float) / np.asarray(mu, dtype=float)
    return float(z.size * (np.log(z.mean()) - np.log(z).mean()))


def projected_utilization(x: np.ndarray, mu: np.ndarray, capacity: float) -> float:
    """Calcula a utilização projetada rho_hat = AM(x/mu) sum(mu) / c."""
    z = np.asarray(x, dtype=float) / np.asarray(mu, dtype=float)
    return float(z.mean() * np.sum(mu) / capacity)


def inefficiency(x: np.ndarray, mu: np.ndarray, capacity: float) -> float:
    """Calcula n (rho_hat - log rho_hat - 1)."""
    rho = projected_utilization(x, mu, capacity)
    return float(np.size(x) * (rho - np.log(rho) - 1.0))


def itakura_saito(x: np.ndarray, y: np.ndarray) -> float:
    """Calcula D_IS(x || y) = sum_r [x_r/y_r - log(x_r/y_r) - 1]."""
    ratio = np.asarray(x, dtype=float) / np.asarray(y, dtype=float)
    return float(np.sum(ratio - np.log(ratio) - 1.0))


# --------------------------------------------------------------------------- 1. Pitágoras
def verify_pythagorean_identity(samples: int, seed: int) -> float:
    """Retorna o maior erro absoluto da decomposição em uma amostra log-normal."""
    rng = np.random.default_rng(seed)
    mu = np.array([1.0, 0.25, 1.0 / 9.0])
    capacity = 10.0
    x_star = capacity * mu / mu.sum()
    maximum_error = 0.0
    for _ in range(samples):
        x = rng.lognormal(mean=0.0, sigma=1.0, size=mu.size)
        error = abs(
            itakura_saito(x, x_star) - unfairness(x, mu) - inefficiency(x, mu, capacity)
        )
        maximum_error = max(maximum_error, error)
    return maximum_error


# --------------------------------------------------------------------------- 2-3. mapa discreto
def synchronized_map(
    weights: np.ndarray,
    capacity: float,
    beta: float,
    cycles: int,
    x0: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Itera o mapa exato x' = beta x + (1-beta) x* entre estados pré-perda."""
    weights = np.asarray(weights, dtype=float)
    x_star = capacity * weights / weights.sum()
    x = np.asarray(x0, dtype=float)
    unfairness_values = []
    utilization_values = []
    for _ in range(cycles + 1):
        unfairness_values.append(unfairness(x, x_star))
        utilization_values.append(projected_utilization(x, x_star, capacity))
        x = beta * x + (1.0 - beta) * x_star
    return np.asarray(unfairness_values), np.asarray(utilization_values), x_star


# --------------------------------------------------------------------------- 4. binomial
def mean_window(
    k: float,
    ell: float,
    loss_probability: float,
    *,
    increase: float = 1.0,
    decrease: float = 0.5,
    rtts: int = 200_000,
    seed: int = 0,
) -> float:
    """Simula a família binomial: aumento a w^{-k} por RTT, queda b w^l por perda."""
    rng = np.random.default_rng(seed)
    window = 10.0
    accumulated = 0.0
    for _ in range(rtts):
        window += increase * window ** (-k)
        losses = rng.binomial(max(int(window), 1), loss_probability)
        for _ in range(losses):
            window = max(window - decrease * window**ell, 1.0)  # piso w >= 1
        accumulated += window
    return accumulated / rtts


def estimate_binomial_exponents(
    rtts: int, seed: int, *, independent_seeds: bool
) -> list[tuple[float, float, float]]:
    """Estima alpha pela inclinação de log E[w] contra log p, para quatro pares (k, l)."""
    probabilities = np.logspace(-4, -2, 8)
    results = []
    for k, ell in [(0.0, 1.0), (-1.0, 1.0), (1.0, 1.0), (0.0, 0.0)]:
        windows = np.array(
            [
                mean_window(k, ell, p, rtts=rtts, seed=seed + (i if independent_seeds else 0))
                for i, p in enumerate(probabilities)
            ]
        )
        slope = np.polyfit(np.log(probabilities), np.log(windows), 1)[0]
        results.append((k, ell, float(-1.0 / slope)))
    return results


# --------------------------------------------------------------------------- 5. interpolação
def partial_equilibrium(
    weights: np.ndarray,
    capacity: float,
    sync_probability: float,
    *,
    decrease: float = 1.0,
    price_gain: float = 50.0,
    dt: float = 2e-4,
    steps: int = 600_000,
) -> np.ndarray:
    """Integra o fluido com intensidade nu_r = Lambda [s + (1-s) x_r/X] até o equilíbrio.

    O preço é a penalidade linear Lambda = price_gain (X - c)_+ ; k = 0, l = 1.
    """
    weights = np.asarray(weights, dtype=float)
    x = np.full_like(weights, capacity / weights.size)
    for _ in range(steps):
        total = x.sum()
        price = price_gain * max(0.0, total - capacity)
        intensity = price * (sync_probability + (1.0 - sync_probability) * x / total)
        x = np.maximum(x + dt * (weights - decrease * intensity * x), 1e-12)
    return x


def estimate_alpha_eff(n: int, sync_probability: float, *, spread: float = 0.25) -> float:
    """Ajuste log-log de x contra a sobre pesos log-espaçados em torno de 1."""
    weights = np.exp(np.linspace(-spread, spread, n))
    x = partial_equilibrium(weights, 10.0, sync_probability)
    return float(1.0 / np.polyfit(np.log(weights), np.log(x), 1)[0])


# --------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=int, default=500, help="pontos aleatórios no item 1")
    parser.add_argument("--rtts", type=int, default=200_000, help="RTTs simulados por ponto no item 4")
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--cycles", type=int, default=16, help="ciclos do mapa discreto nos itens 2-3")
    parser.add_argument("--independent-seeds", action="store_true", help="semente distinta por p no item 4")
    parser.add_argument("--skip-interpolation", action="store_true", help="pula o item 5 (o mais lento)")
    args = parser.parse_args()

    print(f"seed={args.seed}; samples={args.samples}; rtts={args.rtts}; cycles={args.cycles}")

    print("\n[1] identidade pitagórica")
    error = verify_pythagorean_identity(args.samples, args.seed)
    print(f"    erro máximo: {error:.3e}")

    weights = np.array([1.0, 0.25, 1.0 / 9.0])  # RTT = 1, 2, 3  ->  a = 1/T^2
    x0 = np.array([5.0, 3.0, 2.0])  # sobre o plano eficiente: soma = c = 10
    beta = 0.5
    unfair, rho, _ = synchronized_map(weights, 10.0, beta, args.cycles, x0)

    print("\n[2] transiente da utilização projetada (pesos heterogêneos)")
    rho_residual = rho - 1.0
    mask = np.abs(rho_residual[:-1]) > 1e-13  # evita razões de resíduos já cancelados
    rho_ratios = rho_residual[1:][mask] / rho_residual[:-1][mask]
    print(f"    rho_0 = {rho[0]:.4f}  (diferente de 1: o transiente existe)")
    print(f"    razão (rho_{{m+1}}-1)/(rho_m-1) no último ciclo válido: {rho_ratios[-1]:.6f}  (esperada {beta:.3f})")

    print("\n[3] contração transversal")
    ratios = unfair[1:] / unfair[:-1]
    print(f"    injustiça estritamente decrescente em {args.cycles} ciclos? {bool(np.all(np.diff(unfair) < 0))}")
    print(f"    razões por ciclo: {ratios[0]:.3f} -> {ratios[1]:.3f} -> ... -> {ratios[-1]:.6f}  (esperada beta^2 = {beta**2:.3f})")

    print("\n[4] expoentes binomiais  (perda i.i.d. por pacote; "
          f"{'sementes independentes' if args.independent_seeds else 'semente comum'})")
    for k, ell, alpha_hat in estimate_binomial_exponents(
        args.rtts, args.seed, independent_seeds=args.independent_seeds
    ):
        print(f"    k={k:5.2f}, l={ell:4.2f}: alpha teórico={k + ell + 1:.4f}, alpha estimado={alpha_hat:.4f}")

    if args.skip_interpolation:
        return
    print("\n[5] interpolação por sincronização parcial  (alpha_eff = 1 + (1-s)/(s n + 1 - s))")
    print(f"    {'n':>3} {'s':>5} {'teoria':>8} {'medido':>8}")
    for n, s in [(3, 0.10), (3, 0.50), (10, 0.10), (30, 0.02), (30, 0.10)]:
        theory = 1.0 + (1.0 - s) / (s * n + 1.0 - s)
        print(f"    {n:>3} {s:>5.2f} {theory:>8.3f} {estimate_alpha_eff(n, s):>8.3f}")


if __name__ == "__main__":
    main()
