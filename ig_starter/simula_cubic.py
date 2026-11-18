"""Verifica o expoente de escala do CUBIC sob perdas periódicas (alpha = 4/3).

Entre perdas a janela é  w(t) = C (t-K)^3 + Wmax,  K = (Wmax (1-beta)/C)^(1/3),
com ``beta`` a fração RETIDA (w(0) = beta Wmax). O número de pacotes enviados até o
instante T é a integral exata

    P(T) = C [ (T-K)^4 - K^4 ] / 4 + Wmax T,

estritamente crescente em T. Sob perda periódica a perda ocorre quando P(T) = 1/p, e
o tempo do ciclo é obtido por bisseção — não há integração numérica de EDO.

Mapa ciclo-a-ciclo: Wmax' = w(T). Itera-se até o regime e mede-se a janela média
(1/p)/T. Teoria (homogeneidade): w_médio ~ p^{-3/4}, isto é alpha = 4/3.

Também se mede o surrogate binomial (k, l) = (-2/3, 1), dw/dt = w^{2/3}, cujo ciclo
tem primitiva exata w(t) = (w0^{1/3} + t/3)^3. O seu mapa de ciclos é exatamente
auto-similar, e o expoente sai 3/4 em precisão de máquina; o mapa do CUBIC contrai
devagar, e um burn-in curto deixa um transiente visível no expoente (``--show-transient``).
"""

from __future__ import annotations

import argparse

import numpy as np


def _bisect(packets, target: float, upper: float = 1.0, iterations: int = 100) -> float:
    """Menor T com packets(T) >= target, por duplicação da cota e bisseção."""
    lower = 0.0
    while packets(upper) < target:
        upper *= 2.0
    for _ in range(iterations):
        midpoint = 0.5 * (lower + upper)
        if packets(midpoint) < target:
            lower = midpoint
        else:
            upper = midpoint
    return 0.5 * (lower + upper)


def next_cycle_cubic(
    maximum_window: float,
    loss_probability: float,
    *,
    beta: float,
    cubic_constant: float,
) -> tuple[float, float]:
    """Um ciclo do CUBIC: devolve (novo Wmax, janela média do ciclo)."""
    target_packets = 1.0 / loss_probability
    kappa = (maximum_window * (1.0 - beta) / cubic_constant) ** (1.0 / 3.0)

    def packets(time: float) -> float:
        return cubic_constant * ((time - kappa) ** 4 - kappa**4) / 4.0 + maximum_window * time

    elapsed = _bisect(packets, target_packets)
    window = cubic_constant * (elapsed - kappa) ** 3 + maximum_window
    return window, target_packets / elapsed


def next_cycle_binomial(
    maximum_window: float,
    loss_probability: float,
    *,
    beta: float,
    cubic_constant: float,  # ignorado; mantém a assinatura comum
) -> tuple[float, float]:
    """Um ciclo do surrogate (k, l) = (-2/3, 1): dw/dt = w^{2/3}, w0 = beta Wmax."""
    target_packets = 1.0 / loss_probability
    root0 = (beta * maximum_window) ** (1.0 / 3.0)

    def packets(time: float) -> float:
        return 0.75 * ((root0 + time / 3.0) ** 4 - root0**4)

    elapsed = _bisect(packets, target_packets)
    window = (root0 + elapsed / 3.0) ** 3
    return window, target_packets / elapsed


def stationary_mean_window(
    next_cycle,
    loss_probability: float,
    *,
    beta: float,
    cubic_constant: float,
    burn_in: int,
    measured_cycles: int,
) -> float:
    """Descarta o transiente do mapa de máximos e devolve a média das janelas médias."""
    maximum_window = 10.0
    means = []
    for cycle in range(burn_in + measured_cycles):
        maximum_window, mean = next_cycle(
            maximum_window, loss_probability, beta=beta, cubic_constant=cubic_constant
        )
        if cycle >= burn_in:
            means.append(mean)
    return float(np.mean(means))


def fit_exponent(next_cycle, probabilities, **kw) -> tuple[float, float, float]:
    """Ajuste log-log de w_médio contra p: devolve (inclinação, alpha, resíduo máximo)."""
    means = np.array([stationary_mean_window(next_cycle, p, **kw) for p in probabilities])
    coeffs = np.polyfit(np.log(probabilities), np.log(means), 1)
    residual = np.log(means) - np.polyval(coeffs, np.log(probabilities))
    slope = coeffs[0]
    return float(slope), float(-1.0 / slope), float(np.abs(residual).max())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--burn-in", type=int, default=600, help="ciclos descartados (o mapa do CUBIC contrai devagar)")
    parser.add_argument("--cycles", type=int, default=50, help="ciclos medidos após o burn-in")
    parser.add_argument("--beta", type=float, default=0.7, help="fração retida da janela na perda")
    parser.add_argument("--c", type=float, default=0.4, help="constante C do CUBIC")
    parser.add_argument("--show-transient", action="store_true", help="repete o CUBIC com burn-in de 30 ciclos")
    args = parser.parse_args()

    probabilities = np.logspace(-6, -3, 10)
    kw = dict(beta=args.beta, cubic_constant=args.c, burn_in=args.burn_in, measured_cycles=args.cycles)
    print(f"beta={args.beta} (retida); C={args.c}; burn_in={args.burn_in}; ciclos={args.cycles}; "
          f"p em [{probabilities[0]:.0e}, {probabilities[-1]:.0e}]")
    for name, cyc in (("CUBIC exato (integral do ciclo)", next_cycle_cubic),
                      ("surrogate binomial k=-2/3, l=1", next_cycle_binomial)):
        slope, alpha_hat, resid = fit_exponent(cyc, probabilities, **kw)
        print(f"{name:<34} inclinação={slope:+.6f}  alpha={alpha_hat:.6f}  "
              f"(teoria -0.75 / 1.333333)  resíduo máx={resid:.1e}")
    if args.show_transient:
        kw30 = dict(kw, burn_in=30)
        slope, alpha_hat, _ = fit_exponent(next_cycle_cubic, probabilities, **kw30)
        print(f"CUBIC com burn-in de 30 ciclos:     inclinação={slope:+.6f}  alpha={alpha_hat:.6f}  "
              "(transiente do mapa de máximos, não correção ao expoente)")


if __name__ == "__main__":
    main()
