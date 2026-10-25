"""Fig. 5 of the paper: quantum cost against Toffoli depth after all steps, 8 and 32 bits.

The values are those printed by verify_phase11.py, part E. Filled markers are
Pareto-optimal in (quantum cost, Toffoli depth, ancilla inputs).
Run:  python fig_pareto.py      (writes figures/fig_pareto.png and .pdf)
"""
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = {  # n: name -> (cost, tdepth, ancilla)
 8:  {"CLA blocks":(142,9,24),"TSG / Peres RCA":(96,9,8),"Cuccaro":(107,15,2),"VBE":(155,21,8),"Draper":(158,8,13),"Hybrid":(136,7,12)},
 32: {"CLA blocks":(568,33,96),"TSG / Peres RCA":(384,33,32),"Cuccaro":(443,63,2),"VBE":(683,93,32),"Draper":(800,12,59),"Hybrid":(644,11,58)},
}
pareto = {8:{"TSG / Peres RCA","Cuccaro","Hybrid"},32:{"TSG / Peres RCA","Cuccaro","Hybrid"}}
plt.rcParams.update({"font.family":"serif","font.size":9})
fig, axes = plt.subplots(1,2,figsize=(7.2,3.1))
off = {"CLA blocks":(9,-3),"TSG / Peres RCA":(8,-3),"Cuccaro":(-7,-3),"VBE":(-4,-11),"Draper":(9,-3),"Hybrid":(8,-3)}
for ax,n in zip(axes,(8,32)):
    for name,(c,d,a) in rows[n].items():
        p = name in pareto[n]
        ax.scatter(d,c,s=30+a*2.0,marker="o",facecolor="black" if p else "white",edgecolor="black",zorder=3,linewidth=0.9)
        dx,dy = off[name]
        ax.annotate(f"{name} ({a})",(d,c),textcoords="offset points",xytext=(dx,dy),fontsize=7.5,ha="right" if dx<0 else "left")
    ax.set_title(f"{n} bits",fontsize=9)
    ax.set_xlabel("Toffoli depth"); ax.grid(alpha=0.3,linewidth=0.5)
    ax.set_xlim(0, max(d for _,d,_ in rows[n].values())*1.35)
    cs=[c for c,_,_ in rows[n].values()]; ax.set_ylim(min(cs)-0.08*(max(cs)-min(cs)), max(cs)+0.08*(max(cs)-min(cs)))
axes[0].set_ylabel("Quantum cost")
fig.tight_layout()
os.makedirs("figures", exist_ok=True)
for ext,kw in (("png",{"dpi":600}),("pdf",{})):
    fig.savefig(f"figures/fig_pareto.{ext}",**kw)
