import json, random
SECTORS = ["XLC","XLF","XLI","XLB","XLRE","XLU","XLP","XLY","XLK","XLE"]
LABELS = {
    "A":["News","Analysts","Event","Insiders","Peers/Macro","Guidance"],
    "B":["Stacked MAs","RS vs SPY","BB Mid","20D Break","Vol x","Hold 20EMA"],
    "C":["EM Fit","OI/Flow","Blocks/DP","Leaders%>20D","Money Flow","SI/Days"],
    "D":["ATR%","IV%","Correlation","Event Risk","Gap Plan","Sizing/RR"],
    "E":["SPY Trend","Sector Rank","Breadth","VIX Regime","3-Day RS","Drivers"],
    "F":["Trigger","Invalidation","Targets","Time Stop","Slippage","Alerts"],
}
rng = random.Random(7)
out = []
for s in SECTORS:
    cats = {k: {"checks":[{"label": lbl, "score": rng.choice([0,1,2])} for lbl in v]}
            for k,v in LABELS.items()}
    out.append({"symbol": s, "categories": cats})
open("scores.json","w",encoding="utf-8").write(json.dumps(out, indent=2))
print("Wrote scores.json")
