advanced_bayesian_vetting.py
============================

Zweck:
  Separate Slow-Science-Stufe fuer starke Kandidaten, SPCs und HZ-Ziele.
  Dieses Skript gehoert bewusst nicht in masterscript_v2.py.

Aufgaben:
  - GP-Detrending mit sklearn GaussianProcessRegressor
  - lokaler Transit-Fit mit einem glatten Trapezmodell
  - Modellvergleich Transit vs. Flat ueber BIC
  - MCMC nur, wenn emcee installiert ist; sonst wird MCMC_UNAVAILABLE als Flag
    protokolliert
  - Aktivitaetsperioden werden wie im Evidence-Vetting ueber LS/ACF gemessen

CLI:
  - --tic
  - --input-db
  - --input-csv
  - --output-dir
  - --max-candidates
  - --dry-run

Wichtige Eingaben:
  - bevorzugt advanced_bayesian_input.csv aus evidence_vetting.py
  - alternativ die DB-Tabelle evidence_vetting_results
  - als Fallback candidates_v2

Wichtige Ausgaben:
  Jeder Lauf bekommt einen neuen Timestamp-Ordner unter:

    /Users/koni/astro_projects/advanced_bayesian_vetting/YYYYMMDD_HHMMSS_advanced_bayesian_vetting

  Darin:
  - advanced_targets.csv
  - advanced_vetting_results.csv
  - errors.csv, falls noetig
  - run.log

DB-Ausgabe:
  - advanced_vetting_results

Spalten der DB-Tabelle:
  - run_id
  - TIC
  - candidate_id
  - period
  - epoch
  - rotation_period_ls
  - rotation_period_acf
  - activity_score
  - gp_signal_change
  - posterior_period
  - posterior_depth
  - posterior_duration
  - bayes_class
  - evidence_score
  - flags
  - created_at
  - output_dir

Beispiele:
  python3 /Users/koni/astro_projects/scripts/main/advanced_bayesian_vetting.py --input-csv /Users/koni/astro_projects/evidence_vetting/RUN/advanced_bayesian_input.csv --max-candidates 5
  python3 /Users/koni/astro_projects/scripts/main/advanced_bayesian_vetting.py --tic 261107297 --dry-run

Hinweise:
  - bayes_class ist eine Modellvergleichs-Vorsortierung, keine Validierung.
  - Bei fehlendem emcee werden keine MCMC-Unsicherheiten behauptet.
  - Fuer echte posterior-lastige Runs sollte emcee oder ein gleichwertiger
    Sampler installiert werden.
