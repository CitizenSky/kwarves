"""
Habitable-Zone-Rechner nach Kopparapu et al. 2014 (Astrophysical Journal Letters 787:L29).

Berechnet die "Conservative" (Runaway Greenhouse → Maximum Greenhouse) und die
"Optimistic" HZ (Recent Venus → Early Mars) anhand von Teff [K] und L/L_sun.

Ausgabe:
  - HZ-Grenzen in AU (Abstand vom Stern)
  - HZ-Grenzen in Tagen (Umlaufperiode bei gegebener Stern-Masse)
  - Planeten-S_eff (Bestrahlung relativ zur Erde)

Beispiel:
    python scripts/compute_hz.py --teff 4930 --radius 0.78
    python scripts/compute_hz.py --db  # alle Kandidaten aus der DB
"""
from __future__ import annotations
import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

DB_PATH = Path("/Users/koni/astro_projects/database/planet_hunter.db")

# ---------- Kopparapu 2014, Tabelle 1, Polynom-Koeffizienten ----------
#
# S_eff(T) = S_eff_sun + a*T + b*T^2 + c*T^3 + d*T^4
#   wobei T = Teff - 5780 [K]
# Gültig für 2600 K ≤ Teff ≤ 7200 K.
KOPPARAPU = {
    # --- Innerer Rand ---
    "Recent Venus":         dict(S_eff_sun=1.7763, a=1.4335e-4, b=3.3954e-9, c=-7.6364e-12, d=-1.1950e-15),
    "Runaway Greenhouse":   dict(S_eff_sun=1.0385, a=1.2456e-4, b=1.4612e-8, c=-7.6345e-12, d=-1.7511e-15),
    # --- Äußerer Rand ---
    "Maximum Greenhouse":   dict(S_eff_sun=0.3507, a=5.9578e-5, b=1.6707e-9, c=-3.0058e-12, d=-5.1925e-16),
    "Early Mars":           dict(S_eff_sun=0.3207, a=5.4471e-5, b=1.5275e-9, c=-2.1709e-12, d=-3.8282e-16),
}


def s_eff(teff_k: float, edge: str) -> float:
    """Bestrahlungs-Schwellwert (S/S_earth) am gegebenen HZ-Rand."""
    p = KOPPARAPU[edge]
    t = teff_k - 5780.0
    return p["S_eff_sun"] + p["a"]*t + p["b"]*t**2 + p["c"]*t**3 + p["d"]*t**4


def luminosity_solar(teff_k: float, radius_rsun: float) -> float:
    """L/L_sun aus Stefan-Boltzmann: L ∝ R² · T⁴."""
    return (radius_rsun ** 2) * ((teff_k / 5778.0) ** 4)


def hz_distance_au(teff_k: float, radius_rsun: float, edge: str) -> float:
    """HZ-Distanz in AU: d = sqrt(L/S_eff)."""
    L = luminosity_solar(teff_k, radius_rsun)
    return float(np.sqrt(L / s_eff(teff_k, edge)))


def stellar_mass_estimate(teff_k: float, radius_rsun: float) -> float:
    """
    Sehr grobe Mass-Schätzung für Hauptreihen K/M-Zwerge.
    Nutzt Mass-Radius-Relation für die untere Hauptreihe (M ≈ R^1.0 für M-Zwerge,
    M ≈ R^0.8 für K-Zwerge).
    """
    if teff_k < 3700:        # M-Zwerg
        return radius_rsun
    if teff_k < 5300:        # K-Zwerg
        return radius_rsun ** 0.8 * 0.95
    return radius_rsun ** 0.8  # G-Zwerg-Bereich


def period_at_au(au: float, mass_msun: float) -> float:
    """Kepler III: P[Jahre] = sqrt(a³ / M)."""
    p_years = np.sqrt(au ** 3 / mass_msun)
    return float(p_years * 365.25)


@dataclass
class HZResult:
    teff: float
    radius: float
    mass: float
    luminosity: float
    cons_inner_au: float
    cons_outer_au: float
    opt_inner_au:  float
    opt_outer_au:  float
    cons_inner_d:  float
    cons_outer_d:  float
    opt_inner_d:   float
    opt_outer_d:   float

    def as_table(self) -> str:
        return (
            f"  Teff = {self.teff:.0f} K | R* = {self.radius:.3f} R_sun | "
            f"M* ≈ {self.mass:.3f} M_sun | L = {self.luminosity:.4f} L_sun\n"
            f"  Konservative HZ (Runaway → Max. Greenhouse):\n"
            f"     {self.cons_inner_au:.3f} – {self.cons_outer_au:.3f} AU   "
            f"(Periode {self.cons_inner_d:.1f} – {self.cons_outer_d:.1f} d)\n"
            f"  Optimistische HZ (Recent Venus → Early Mars):\n"
            f"     {self.opt_inner_au:.3f} – {self.opt_outer_au:.3f} AU   "
            f"(Periode {self.opt_inner_d:.1f} – {self.opt_outer_d:.1f} d)"
        )

    def classify_period(self, period_days: float) -> str:
        if period_days < self.opt_inner_d:
            return "ZU HEISS"
        if period_days < self.cons_inner_d:
            return "Optimistisch HZ (heisse Kante)"
        if period_days <= self.cons_outer_d:
            return "★ KONSERVATIVE HZ ★"
        if period_days <= self.opt_outer_d:
            return "Optimistisch HZ (kalte Kante)"
        return "ZU KALT"


def compute(teff: float, radius: float, mass: Optional[float] = None) -> HZResult:
    if mass is None:
        mass = stellar_mass_estimate(teff, radius)
    L = luminosity_solar(teff, radius)
    cins = hz_distance_au(teff, radius, "Runaway Greenhouse")
    cout = hz_distance_au(teff, radius, "Maximum Greenhouse")
    oins = hz_distance_au(teff, radius, "Recent Venus")
    oout = hz_distance_au(teff, radius, "Early Mars")
    return HZResult(
        teff=teff, radius=radius, mass=mass, luminosity=L,
        cons_inner_au=cins, cons_outer_au=cout,
        opt_inner_au=oins,  opt_outer_au=oout,
        cons_inner_d=period_at_au(cins, mass),
        cons_outer_d=period_at_au(cout, mass),
        opt_inner_d =period_at_au(oins, mass),
        opt_outer_d =period_at_au(oout, mass),
    )


# ---------- DB-Driver ----------

def collect_db_targets(conn: sqlite3.Connection) -> list[dict]:
    """Sammelt alle bekannten Kandidaten + zugehörige Sternparameter."""
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT pc.TIC,
               pc.typ,
               pc.best_period AS pc_period,
               pc.teff        AS pc_teff,
               pc.stellar_radius AS pc_sr,
               r.teff         AS r_teff,
               r.radius       AS r_radius,
               r.distance_ly  AS r_dist,
               s.teff         AS s_teff,
               s.radius       AS s_radius,
               b.best_period  AS b_period
        FROM planet_candidates pc
        LEFT JOIN rohdaten       r ON r.TIC    = pc.TIC
        LEFT JOIN stars          s ON s.TIC    = pc.TIC
        LEFT JOIN bls_candidates b ON b.tic_id = pc.TIC
    """).fetchall()
    out = []
    for tic, typ, pc_per, pc_teff, pc_sr, r_teff, r_radius, r_dist, s_teff, s_radius, b_per in rows:
        teff   = pc_teff or r_teff or s_teff
        radius = pc_sr   or r_radius or s_radius
        period = pc_per or b_per
        out.append(dict(TIC=tic, typ=typ, teff=teff, radius=radius,
                        distance_ly=r_dist, period=period))

    # Plus die HZ-Tabelle (eigene Quelle)
    for tic, sr, _rpe, _cls, _s, _e, _check in cur.execute(
        "SELECT tic_id, star_radius, planet_radius_earth, classification, "
        "HZ_Start_Tage, HZ_Ende_Tage, HZ_Check FROM hz_candidates"
    ).fetchall():
        # Teff schätzen: K-Zwerg-Median, falls nicht explizit bekannt
        out.append(dict(TIC=tic, typ="HZ_candidate", teff=4500.0, radius=sr,
                        distance_ly=None, period=None))
    return out


def cmd_db():
    conn = sqlite3.connect(DB_PATH)
    targets = collect_db_targets(conn)

    print("=" * 90)
    print("HABITABLE-ZONE-BERECHNUNG NACH KOPPARAPU 2014")
    print("=" * 90)
    print(f"{'TIC':>11} {'Teff':>6} {'R*':>6} {'P[d]':>8} {'cons. HZ [d]':>16} "
          f"{'opt. HZ [d]':>16}  Klassifikation")
    print("-" * 90)

    for t in targets:
        if t["teff"] is None or t["radius"] is None:
            print(f"{t['TIC']:>11} {'-':>6} {'-':>6} {'-':>8} "
                  f"{'(keine Sternparameter)':>34}")
            continue

        try:
            hz = compute(t["teff"], t["radius"])
        except Exception as e:
            print(f"{t['TIC']:>11} ERROR: {e}")
            continue

        per = t["period"]
        per_str = f"{per:.3f}" if per else "-"
        cls = hz.classify_period(per) if per else "(keine Periode)"

        print(f"{t['TIC']:>11} {t['teff']:>6.0f} {t['radius']:>6.3f} {per_str:>8} "
              f"{hz.cons_inner_d:>6.1f}–{hz.cons_outer_d:<7.1f}  "
              f"{hz.opt_inner_d:>6.1f}–{hz.opt_outer_d:<7.1f}   {cls}")

    conn.close()


def cmd_single(teff: float, radius: float, period: Optional[float] = None):
    hz = compute(teff, radius)
    print("HZ-BERECHNUNG (Kopparapu 2014)")
    print("=" * 60)
    print(hz.as_table())
    if period is not None:
        print(f"\nPlaneten-Periode {period:.3f} d → {hz.classify_period(period)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--teff",   type=float, help="Teff [K]")
    ap.add_argument("--radius", type=float, help="Stellar radius [R_sun]")
    ap.add_argument("--period", type=float, default=None, help="Planeten-Periode [d]")
    ap.add_argument("--db", action="store_true", help="alle DB-Kandidaten durchgehen")
    args = ap.parse_args()

    if args.db:
        cmd_db()
    elif args.teff and args.radius:
        cmd_single(args.teff, args.radius, args.period)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
