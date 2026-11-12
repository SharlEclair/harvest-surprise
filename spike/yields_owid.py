import io, requests, pandas as pd
H={"User-Agent":"Mozilla/5.0 research-probe"}
r=requests.get("https://ourworldindata.org/grapher/maize-yields.csv?csvType=full",headers=H,timeout=60)
df=pd.read_csv(io.StringIO(r.text))
us=df[df.Entity=="United States"].copy()
us.columns=["entity","code","year","yield_t_ha"]
us["yield_bu_ac"]=us.yield_t_ha*39.3681/2.47105
us=us[(us.year>=1995)].sort_values("year")
us.to_csv("spike/data/us_maize_yield_owid.csv",index=False)
print(us.tail(12).to_string(index=False))
print("rows",len(us),"min",us.year.min(),"max",us.year.max())
