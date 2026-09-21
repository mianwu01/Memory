"""Export real discovered associations and observed development comparisons."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def run(base):
    base=Path(base);report=json.loads((base/'report.json').read_text());fit=report['fit']
    fig,axes=plt.subplots(1,3,figsize=(16,5),gridspec_kw={'width_ratios':[1,1,1.6]})
    labels=[f"T{i}: "+'/'.join(words[:3]) for i,words in enumerate(report['topics'])]
    for ax,key,title in [(axes[0],'primary','Primary projected-write lag associations'),(axes[1],'within_task_centered_diagnostic','After within-task centering (diagnostic)')]:
        a=np.asarray(fit[key]['adjacency'],dtype=int).T
        ax.imshow(a,vmin=0,vmax=1,cmap='Blues')
        ax.set_xticks(range(4),[f'T{i}' for i in range(4)]);ax.set_yticks(range(4),[f'T{i}' for i in range(4)])
        ax.set_xlabel('Source at previous native write');ax.set_ylabel('Target at current native write');ax.set_title(title,fontsize=10)
        for i in range(4):
            for j in range(4):ax.text(j,i,str(a[i,j]),ha='center',va='center',color='white' if a[i,j] else '#333333')
    names=['discovered','complete','topic_only','bm25_matched','recency_matched','last_answer_reuse','question_answer_reuse','query_only','full']
    values=[report['methods'][m]['correct']/report['methods'][m]['n'] for m in names]
    axes[2].barh(names,values,color=['#146b8c']+['#879aa5']*(len(names)-1))
    axes[2].invert_yaxis();axes[2].set_xlim(0,1.12);axes[2].set_xlabel('Strict exact-match proportion, fixed dev cases')
    for i,(name,value) in enumerate(zip(names,values)):
        r=report['methods'][name];axes[2].text(value+.015,i,f"{r['correct']}/{r['n']}",va='center',fontsize=9)
    axes[2].set_title('In-sample development comparison; shared inputs share calls',fontsize=10)
    fig.suptitle('Progressive Search: actual native writes, lossy topic measurements — not semantic SCM recovery',fontsize=12)
    fig.text(.02,.025,' | '.join(labels),fontsize=8)
    fig.tight_layout(rect=(0,.065,1,.94));fig.savefig(base/'structure_and_results.svg');fig.savefig(base/'structure_and_results.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='results/development/progressive_search');run(p.parse_args().base)
