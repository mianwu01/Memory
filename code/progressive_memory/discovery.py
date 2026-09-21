"""Exploratory PCMCI+ on explicit, lossy projections of native write states."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import time
import warnings

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF
from sklearn.linear_model import Ridge
from tigramite import data_processing as pp
from tigramite.pcmci import PCMCI
from tigramite.independence_tests.parcorr import ParCorr
from .runtime import save


def trajectories(directory,start,end):
    return [json.loads((Path(directory)/f'case_{i:03d}'/'trajectory.json').read_text()) for i in range(start,end)]


class Projection:
    def fit(self,trajectories):
        entries=[e for t in trajectories for e in t['entries']]
        self.vectorizer=TfidfVectorizer(stop_words='english',max_features=4096,min_df=2,max_df=.98)
        x=self.vectorizer.fit_transform(entries)
        self.nmf=NMF(n_components=4,init='nndsvda',random_state=22,max_iter=1000)
        with warnings.catch_warnings(record=True) as caught:
            self.nmf.fit(x)
        self.warnings=[str(w.message) for w in caught]
        return self

    def transform(self,texts):return self.nmf.transform(self.vectorizer.transform(texts))

    def metadata(self):
        words=self.vectorizer.get_feature_names_out()
        return dict(vocabulary=words.tolist(),idf=self.vectorizer.idf_.tolist(),components=self.nmf.components_.tolist(),
                    top_words=[[str(words[i]) for i in np.argsort(c)[-20:][::-1]] for c in self.nmf.components_],
                    reconstruction_error=float(self.nmf.reconstruction_err_),iterations=self.nmf.n_iter_,warnings=self.warnings)


def load_projection(path):
    projection=Projection();projection.__dict__.update(pickle.loads(Path(path).read_bytes()))
    return projection


def fit_panel(panel):
    # Each task stays separate: no lag can cross a task boundary.
    frame=pp.DataFrame({i:x for i,x in enumerate(panel)},analysis_mode='multiple',var_names=[f'write_topic_{i}' for i in range(4)])
    pcmci=PCMCI(dataframe=frame,cond_ind_test=ParCorr(significance='analytic'),verbosity=0)
    fit=pcmci.run_pcmciplus(tau_min=1,tau_max=1,pc_alpha=.05,max_conds_dim=1,max_conds_py=1,max_conds_px=1)
    p=fit['p_matrix'][:,:,1].copy()
    flat=p.ravel();order=np.argsort(flat);adjusted=np.empty_like(flat)
    adjusted[order]=np.minimum(1,np.minimum.accumulate((flat[order]*len(flat)/np.arange(1,len(flat)+1))[::-1])[::-1])
    q=adjusted.reshape(p.shape)
    adjacency=(q<=.05)&np.isfinite(q)
    return dict(p=p.tolist(),q=q.tolist(),value=fit['val_matrix'][:,:,1].tolist(),native_graph=fit['graph'].tolist(),adjacency=adjacency.tolist())


def run(args):
    started=time.monotonic()
    out=Path(args.out)
    dev=trajectories(args.dev,0,10)
    training=trajectories(args.training,args.start,args.end)
    protocol=Path('docs/progressive-structure-measurement-2026-09-22.md')
    save(out/'config.json',dict(training_cases=[t['case'] for t in training],projection_cases=[t['case'] for t in dev],
          scope=args.scope,protocol=protocol.read_text(),source=Path(__file__).read_text(),
          versions={package:version(package) for package in ['numpy','scikit-learn','tigramite']}))
    projection=Projection().fit(dev)
    out.mkdir(parents=True,exist_ok=True)
    artifact=out/'projection.pkl'
    if artifact.exists():raise RuntimeError('Do not refit an existing discovery artifact')
    artifact.write_bytes(pickle.dumps(projection.__dict__))
    save(out/'projection.json',projection.metadata())
    panels=[];queries=[];observations=[]
    for t in training:
        w=projection.transform(t['entries']);q=projection.transform([e['query'] for e in t['events']])
        panels.append(w);queries.append(q)
        observations.append(dict(case=t['case'],increments=w.tolist(),query_projection=q.tolist(),cumulative_state=w.cumsum(axis=0).tolist(),
                                 actual_snapshot_sha256=[hashlib.sha256(e['write']['after'].encode()).hexdigest() for e in t['events']],
                                 native_retained_all=t['all_memory_retained']))
    regression=Ridge(alpha=1).fit(np.concatenate(queries),np.concatenate(panels))
    residuals=[w-regression.predict(q) for w,q in zip(panels,queries)]
    save(out/'observations.json',observations)
    result=fit_panel(residuals);raw=fit_panel(panels)
    centered=fit_panel([x-x.mean(axis=0,keepdims=True) for x in residuals])
    boot=[]
    for i in range(20):
        rng=np.random.default_rng(2200+i);sample=[residuals[j] for j in rng.integers(0,len(residuals),len(residuals))]
        try:boot.append(dict(seed=2200+i,fit=fit_panel(sample)))
        except (ValueError,ZeroDivisionError) as error:boot.append(dict(seed=2200+i,error=type(error).__name__))
    rng=np.random.default_rng(2300)
    shuffled=fit_panel([x[rng.permutation(len(x))] for x in residuals])
    frequency=np.mean([b['fit']['adjacency'] for b in boot if 'fit' in b],axis=0)
    save(out/'fit.json',dict(scope=args.scope,primary=result,unadjusted=raw,within_task_centered_diagnostic=centered,time_shuffle=shuffled,bootstrap=boot,bootstrap_frequency=frequency.tolist(),
        execution_seconds=time.monotonic()-started,
        ridge_coefficients=regression.coef_.tolist(),ridge_intercept=regression.intercept_.tolist(),
        trajectory_lengths=[len(x) for x in panels],lag1_pairs=sum(len(x)-1 for x in panels),
        effective_pcmci_samples=sum(max(0,len(x)-2) for x in panels),
        residual_std=np.std(np.concatenate(residuals),axis=0).tolist(),
        limitations=['Lossy text projection, not native semantic fields','Query residualization is linear only','Heterogeneous tasks may violate shared mechanisms','Small independent trajectory count','Append-only cumulative state; discovery uses increments']))
    print(json.dumps(dict(edges=int(np.sum(result['adjacency'])),lag1_pairs=sum(len(x)-1 for x in panels),topics=projection.metadata()['top_words'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dev',required=True);p.add_argument('--training',required=True);p.add_argument('--start',type=int,default=0);p.add_argument('--end',type=int,default=10);p.add_argument('--scope',choices=['development_in_sample','held_out_training'],required=True);p.add_argument('--out',required=True);run(p.parse_args())
