import pandas as pd, numpy as np
from scipy import stats
d=pd.read_csv("spike/data/spike_merged.csv")
x=d.ndvi_dt.to_numpy(); y=d.yield_dt.to_numpy()
sl,ic,r,p,se=stats.linregress(x,y)
print(f"slope {sl:.1f} bu/ac per 1.0 NDVI  (se {se:.1f}), r={r:.3f}, r2={r*r:.2f}, p={p:.4f}, n={len(d)}")
print(f"=> +0.01 NDVI anomaly = {sl*0.01:.2f} bu/ac")
print(f"intercept {ic:.2f}, resid sd {np.std(y-(ic+sl*x),ddof=2):.2f}")
m=d.year!=2012
sl2,ic2,r2,p2,se2=stats.linregress(x[m],y[m])
print(f"without 2012: r={r2:.3f} p={p2:.4f} n={m.sum()} slope {sl2:.1f}")
print(f"Spearman {stats.spearmanr(x,y).statistic:.3f}")
print("worst misses:", d.assign(err=y-(ic+sl*x)).reindex(d.assign(err=y-(ic+sl*x)).err.abs().sort_values(ascending=False).index)[["year","yield_dt","ndvi_dt","err"]].head(4).round(2).to_dict("records"))
