# Data dictionary

Everything the pipeline writes, what it is, and how it is keyed. Files under
`data/raw/` are immutable pulls; `data/processed/` is derived and safe to rebuild.

## data/raw

| file | grain | key | source |
|---|---|---|---|
| `nass_yield.csv` | state x year x vintage period | state_alpha, year, reference_period_desc | NASS Quick Stats |
| `nass_area_harvested.csv` | state x year | state_alpha, year | NASS Quick Stats |
| `nass_area_planted.csv` | state x year | state_alpha, year | NASS Quick Stats |
| `nass_condition.csv` | state x week x category | state_alpha, week_ending, short_desc | NASS Quick Stats |
| `wasde_corn.csv` | release x market year x attribute | ReleaseDate, MarketYear, Attribute | USDA WASDE data files |
| `prices_daily.csv` | date x ticker | date, ticker | Yahoo (front-month continuous, NOT roll-adjusted) |
| `rice_price.csv` | year | year | annual mean of `ZR=F` |
| `rice_daily.csv` | date | date | `ZR=F` daily bars |
| `weather_state_year.csv` | state x year | state_alpha, year | NASA POWER, 3 points per state |
| `cdec_reservoirs.csv` | station x date | station, date | CDEC sensors 6 (elevation ft) and 15 (storage AF) |

## data/processed

| file | grain | what it supports |
|---|---|---|
| `gate0_events.csv` | WASDE release | yield revision and one-day returns |
| `gate0_leadtime.csv` | lead in days | oracle P&L at 0/1/2/3/5/10 days |
| `gate0_surface.csv` | forecast RMSE | break-even surface |
| `gate1_predictions.csv` | state x year x model x scheme | corn yield predictions (`scheme` is loyo or expanding) |
| `gate1_metrics.csv` | model x scheme | RMSE, MAE, bias, R2 |
| `gate1_national.csv` | year x model | acreage-weighted national aggregate |
| `gate2_state.csv` / `gate2_national.csv` | state-year / year | model-vs-USDA disagreement and revision |
| `gate2_trades.csv` | year | costed Aug-to-Jan trades |
| `reservoir_v2_*.npz` | scene x grid cell | water and valid fractions on a fixed 0.001 deg grid |
| `reservoir_v2_validation.csv` | reservoir | Spearman, LOO RMSE, baseline |
| `reservoir_v2_matched.csv` | reservoir x date | area and gauge elevation |
| `chain_propagation.csv` | reservoir | storage error -> acreage error |
| `mc_propagation.csv` | quantity | Monte Carlo distribution of elasticity and RMSE |
| `water_rice.csv` | year | rice acres and 1 April storage |
| `rice_surprise.csv` | year | March and June acreage, revision |
| `resolution_grid.csv` | signal x sensor | physics verdict |

## Conventions

- `scheme` is `loyo` (leave-one-year-out, flatters the model) or `expanding`
  (point-in-time, the honest one). Any claim about what a trader could do uses
  `expanding`.
- Prices are front-month continuous and **not** roll-adjusted; one-day moves
  above 10% on non-release dates are contract splices.
- Missing NASS values are `(D)` or `(Z)` strings and are coerced to NaN, never
  to zero.
