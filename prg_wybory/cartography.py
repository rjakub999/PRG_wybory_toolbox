"""Same palette/classes in ArcGIS renderer and standalone exports."""
from collections import Counter
import colorsys
import hashlib
import shapely

COLORS={'TRZASKOWSKI':'#245a9f','NAWROCKI':'#c55c16','MENTZEN':'#6d4595','ZANDBERG':'#25846d'}
CLASSES=['<30%', '30–<40%', '40–<50%', '50–<60%', '≥60%']
SAT=[.28,.45,.62,.80,1.]


def color(leader,category):
    if leader=='REMIS': return '#b1b4b9'
    if leader=='BRAK_GLOSOW': return '#eeeeee'
    if leader in COLORS:
        base=tuple(int(COLORS[leader][i:i+2],16)/255 for i in (1,3,5))
    else:
        hue=int(hashlib.sha256(leader.encode()).hexdigest()[:8],16)/0xffffffff
        base=colorsys.hsv_to_rgb(hue,.65,.7)
    rgb=[round(255*(1-(1-c)*SAT[category])) for c in base]
    return '#'+''.join(f'{c:02x}' for c in rgb)


def label(leader,category,names):
    if leader=='REMIS': return 'Remis'
    if leader=='BRAK_GLOSOW': return 'Brak głosów ważnych'
    return f'{names.get(leader,leader).replace("_"," ")} · {CLASSES[category]}'


def export_maps(rows,rounds,directory,city,election,crs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch, Patch, Rectangle
    from matplotlib.ticker import MaxNLocator
    all_geoms=[r['geometry'] for r in rows]
    xmin,ymin,xmax,ymax=shapely.total_bounds(all_geoms)
    summary={}
    for turn in (1,2):
        counts=Counter(r['properties'][f'T{turn}_LIDER'] for r in rows)
        names=rounds[turn-1]['candidates']
        fig=plt.figure(figsize=(14,10),facecolor='white')
        ax=fig.add_axes([.04,.24,.92,.63]); ax.set_aspect('equal'); ax.axis('off')
        for r in rows:
            a=r['properties']; leader=a[f'T{turn}_LIDER']; category=a[f'T{turn}_KLASA']
            for poly in shapely.get_parts(shapely.orient_polygons(r['geometry'])):
                vertices=[]; codes=[]
                for ring in [poly.exterior,*poly.interiors]:
                    coords=list(ring.coords); vertices.extend(coords)
                    codes.extend([Path.MOVETO]+[Path.LINETO]*(len(coords)-2)+[Path.CLOSEPOLY])
                ax.add_patch(PathPatch(Path(vertices,codes),facecolor=color(leader,category),
                    edgecolor='#ffffff',lw=.35,hatch='////' if leader=='REMIS' else None))
        for poly in shapely.get_parts(shapely.union_all(all_geoms)):
            ax.plot(*poly.exterior.xy,color='#596570',lw=.6)
        pad=max(xmax-xmin,ymax-ymin)*.025
        ax.set_xlim(xmin-pad,xmax+pad); ax.set_ylim(ymin-pad*2,ymax+pad)
        width=xmax-xmin
        length=max(x for x in MaxNLocator(nbins=5).tick_values(0,width/4) if 0<x<=width/4)
        bx,by=xmin,ymin-pad
        for i in range(2):
            ax.add_patch(Rectangle((bx+i*length/2,by),length/2,pad*.12,facecolor='black' if i==0 else 'white',edgecolor='black',lw=.5))
        ax.text(bx,by-pad*.25,'0',fontsize=8,va='top')
        ax.text(bx+length,by-pad*.25,f'{length/1000:g} km',fontsize=8,va='top',ha='center')
        ax.annotate('N',xy=(.98,.98),xytext=(.98,.85),xycoords='axes fraction',ha='center',arrowprops=dict(arrowstyle='-|>'))
        fig.text(.045,.95,f'{city} · {election}',fontsize=22,weight='bold')
        fig.text(.045,.912,f'{"I" if turn==1 else "II"} tura · kandydat z największą liczbą głosów',fontsize=14)
        fig.text(.045,.18,'Kolor: lider obwodu · nasycenie: udział lidera w głosach ważnych',fontsize=11)
        handles=[]
        for leader in sorted(counts,key=lambda n:(-counts[n],n)):
            categories=sorted({r['properties'][f'T{turn}_KLASA'] for r in rows if r['properties'][f'T{turn}_LIDER']==leader})
            for category in categories:
                handles.append(Patch(facecolor=color(leader,category),edgecolor='#aaa',hatch='////' if leader=='REMIS' else None,label=label(leader,category,names)))
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.04,.165),frameon=False,ncol=3,fontsize=8)
        fig.text(.045,.025,f'{len(rows)} obwodów stałych · wyniki PKW · {crs} · nasycenie nie oznacza frekwencji',fontsize=8,color='#596570')
        stem=directory/f'kartogram_T{turn}'
        for ext in ('png','pdf'):
            fig.savefig(str(stem)+'.'+ext,dpi=200,facecolor='white')
        plt.close(fig)
        summary[turn]=dict(liderzy=dict(counts),remisy=[r['properties']['NR_KOMISJI'] for r in rows if r['properties'][f'T{turn}_LIDER']=='REMIS'])
    return summary
