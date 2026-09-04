#!/usr/bin/env python3
"""trigger_cnn.py — a convolutional network on spectrograms, measured against the trees.

The idea is Charles's (2026-09-04): rather than hand-crafting numbers that summarise the
spectrum, hand the model the spectrogram and let it find its own. The motivation is
specific and was earned the hard way -- the 17 tabular features collapse the window into
ONE spectrum, so the spectrum's EVOLUTION is destroyed before the model sees it, and
coda_probe.py showed that evolution is real and measurable but could not be squeezed into
two hand-made columns. A spectrogram carries it natively.

    trees, 17 tabular features   PR-AUC 0.899 on the displayed slice
    MLP [18,64,1] on the same    PR-AUC 0.914, seed spread 0.011
    this CNN on spectrograms     PR-AUC 0.392, train 0.778 -- memorising

>>> MEASURED RESULT (2026-09-04): DOES NOT BEAT THE TREES HERE, YET, LIKE THIS. <<<

Out-of-fold 0.392 against a training score of 0.778: the model fits what it is shown and
does not transfer. That is 27 distinct earthquakes, and it is a statement about THIS
architecture with THIS preprocessing at THIS sample size -- not about spectrogram CNNs.
cnn_learning_curve.py measures which: the curve is STILL CLIMBING at 27 events
(+0.0124 PR-AUC per event, no sign of bending), so the binding constraint is data.

TWO BUGS OF MINE CAME FIRST, and both are more useful than the result, because each one
looked exactly like "the idea does not work":

  1. BATCH COMPOSITION. The obvious thing -- BCEWithLogitsLoss(pos_weight=n_neg/n_pos)
     over shuffled batches -- could not fit even the TRAINING set (PR-AUC 0.06 with 39
     positives and 1,300 parameters, which it should have memorised effortlessly). At
     0.3% positives with batch 256, about half of all batches contain no earthquake at
     all and the rest carry one example weighted 312x. Sampling a fixed fraction of
     positives into every batch took the training score 0.06 -> 0.76. AT EXTREME
     IMBALANCE, FIX THE BATCH, NOT THE LOSS.
  2. THE POOLING BOTTLENECK. AdaptiveAvgPool2d(1) averages over BOTH axes. Averaging over
     time was wanted; averaging over FREQUENCY threw away the one thing a spectrogram is
     for, one layer before the decision. Keeping six frequency bands cost 80 parameters
     and returned 27% (0.310 -> 0.392) with a 3x smaller seed spread.

Neither was visible from the out-of-fold score alone. The train-vs-out-of-fold gap is
what separated "never learned" from "memorised", and they need opposite fixes.

THE ARCHITECTURE IS DELIBERATELY TINY, and the head is where the thought went. A flatten
into a dense layer would cost ~20,000 parameters -- 585 per real earthquake, hopeless at
this data size. GLOBAL AVERAGE POOLING over the channels costs none: it reduces each
feature map to its mean, so the head is one weight per channel. Total ~1,300 parameters,
which is the same territory as the MLP that beat the trees.

Global average pooling also buys a property worth having for free: the model becomes
insensitive to WHERE in the window a pattern occurs. A trigger's arrival wanders by
seconds, and we do not want the network keying on absolute position.

DROPOUT IS THE POINT OF USING TORCH AT ALL. The MLP experiment found depth collapsing
(one hidden layer 0.91, two 0.51) with L2 as the only regulariser, which sklearn's
MLPClassifier is limited to. Yeck et al. put 20% dropout on EVERY layer of their CNNs and
said so explicitly. This does the same, and is the first model here that can.

WHAT IS HELD FIXED SO THE COMPARISON MEANS SOMETHING: the same rows, the same
StratifiedGroupKFold with the same seed, positives grouped by catalogue event and
negatives by day, and every number computed on real rows. Several seeds per fold, because
the MLP work showed a single seed can swing PR-AUC from 0.49 to 0.90 and "prove" whatever
you hoped -- seed 0 of the deep net beat the trees and seeds 1 and 2 were catastrophic.

    analysis/.venv/bin/python analysis/trigger_cnn.py --data data/spec55.npz
"""
import argparse
import os

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))


class SpecCNN(nn.Module):
    """(1, freq, time) -> one logit. Two conv blocks, global average pool, one weight
    per channel. About 1,300 parameters."""

    def __init__(self, c1=8, c2=16, p_drop=0.2, head=0, n_freq_keep=6):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, c1, 3, padding=1), nn.BatchNorm2d(c1), nn.ReLU(),
            nn.MaxPool2d(2), nn.Dropout(p_drop),
            nn.Conv2d(c1, c2, 3, padding=1), nn.BatchNorm2d(c2), nn.ReLU(),
            nn.MaxPool2d(2), nn.Dropout(p_drop),
            # POOL OVER TIME ONLY, KEEPING FREQUENCY. AdaptiveAvgPool2d(1) -- global
            # average pooling -- was the first version and it averages over BOTH axes.
            # Averaging over time is wanted: an arrival wanders by seconds and the model
            # should not key on absolute position. Averaging over FREQUENCY throws away
            # the one thing the picture is for. A filter detecting "sharp broadband
            # onset" returned a single number whether it fired at 2 Hz or 40 Hz, so a
            # truck and an earthquake could produce near-identical channel means while
            # looking nothing alike -- which is precisely the distinction being learned.
            # The tree model's two strongest features are frac_1_3 and frac_3_8, both
            # frequency-resolved; a head that cannot tell low from high is working
            # without the information that separates the classes.
            nn.AdaptiveAvgPool2d((n_freq_keep, 1)),
        )
        self.pooled = c2 * n_freq_keep
        # A wider final conv means the pooled vector the head sees is longer. The first
        # version pooled 16 channels straight to one logit and UNDERFITTED badly --
        # train PR-AUC 0.059, so it never learned the training set, let alone
        # generalised. Global average pooling is the right idea for the parameter budget
        # but 16 numbers is not enough to describe a spectrogram. An optional hidden
        # layer after the pool costs little and gives the head somewhere to work.
        self.head = (nn.Linear(self.pooled, 1) if not head else
                     nn.Sequential(nn.Linear(self.pooled, head), nn.ReLU(),
                                   nn.Dropout(p_drop), nn.Linear(head, 1)))

    def forward(self, x):
        return self.head(self.net(x).flatten(1)).squeeze(1)


def fit_one(Xtr, ytr, Xte, seed, epochs, lr, pos_weight, device, p_drop,
            c1=8, c2=16, head=0, nfk=6):
    torch.manual_seed(seed)
    m = SpecCNN(c1=c1, c2=c2, p_drop=p_drop, head=head, n_freq_keep=nfk).to(device)
    opt = torch.optim.Adam(m.parameters(), lr=lr, weight_decay=1e-4)
    # BALANCED BATCHES, not a giant pos_weight. The first version did the obvious thing --
    # BCEWithLogitsLoss(pos_weight = n_neg/n_pos) with shuffled batches -- and could not
    # fit even the TRAINING set (PR-AUC 0.06 with 39 positives and 1,313 parameters,
    # which it should have memorised effortlessly). The reason is batch composition: at
    # 0.3% positives and batch 256, about half the batches contain no earthquake at all,
    # and the ones that do carry a single example weighted 312x. Most steps therefore
    # learn "everything is noise" and the rest lurch. Sampling a fixed fraction of
    # positives into every batch fixes it, and the loss weight can then drop to something
    # sane because the batch is already balanced.
    lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min(pos_weight, 4.0),
                                                         device=device))
    Xtr_t = torch.from_numpy(Xtr).unsqueeze(1).to(device)
    ytr_t = torch.from_numpy(ytr.astype(np.float32)).to(device)
    pos = np.flatnonzero(ytr == 1)
    neg = np.flatnonzero(ytr == 0)
    bs, frac_pos = 128, 0.25
    n_pos_b = max(1, int(bs * frac_pos))
    n_neg_b = bs - n_pos_b
    steps = max(1, len(neg) // n_neg_b)
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        m.train()
        negp = rng.permutation(neg)
        for i in range(steps):
            nb = negp[i * n_neg_b:(i + 1) * n_neg_b]
            pb = rng.choice(pos, n_pos_b, replace=len(pos) < n_pos_b)
            idx = torch.from_numpy(np.concatenate([pb, nb])).to(device)
            opt.zero_grad()
            loss = lossf(m(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()
    m.eval()
    return predict(m, Xte, device), m


def predict(m, X, device, bs=512):
    """Scores for X, in batches so a big training fold does not have to fit at once."""
    m.eval()
    out = []
    with torch.no_grad():
        Xt = torch.from_numpy(X).unsqueeze(1)
        for i in range(0, len(Xt), bs):
            out.append(torch.sigmoid(m(Xt[i:i + bs].to(device))).cpu().numpy())
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data", "spec55.npz"))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--c1", type=int, default=8)
    ap.add_argument("--c2", type=int, default=16)
    ap.add_argument("--head", type=int, default=0, help="hidden units after the pool; 0 = none")
    ap.add_argument("--nfk", type=int, default=6,
                    help="frequency bands kept after pooling; 1 = the old global pool")
    ap.add_argument("--baseline", type=float, default=0.899)
    a = ap.parse_args()

    d = np.load(a.data, allow_pickle=True)
    X, y, groups = d["X"], d["y"], d["groups"]
    device = "mps" if torch.backends.mps.is_available() else "cpu"

    m = SpecCNN(c1=a.c1, c2=a.c2, p_drop=a.dropout, head=a.head, n_freq_keep=a.nfk)
    npar = sum(p.numel() for p in m.parameters())
    nev = len(set(groups[y == 1]))
    print(f"data {X.shape}  {int(y.sum())} quake / {len(y)} rows, {nev} distinct events")
    print(f"model {npar} parameters, {npar/max(1,int(y.sum())):.0f} per positive")
    print(f"device {device}, {a.seeds} seeds x 5 folds, {a.epochs} epochs, "
          f"dropout {a.dropout}\n")

    oof = np.full((a.seeds, len(y)), np.nan)
    tr_scores = []
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for k, (tr, te) in enumerate(cv.split(X, y, groups)):
        pw = float((y[tr] == 0).sum() / max(1, (y[tr] == 1).sum()))
        for s in range(a.seeds):
            p, mdl = fit_one(X[tr], y[tr], X[te], s, a.epochs, a.lr, pw, device,
                             a.dropout, a.c1, a.c2, a.head, a.nfk)
            oof[s, te] = p
            # Score the TRAINING fold too. If this is high while out-of-fold is low the
            # model memorised; if both are low it never fitted at all. That distinction
            # is what separated overfitting from optimisation failure in the MLP run,
            # and it is not visible from the out-of-fold number alone.
            tr_scores.append(average_precision_score(y[tr], predict(mdl, X[tr], device)))
        print(f"  fold {k+1}/5 done", flush=True)

    print(f"\n{'seed':>5}  {'PR-AUC':>8}  {'ROC':>8}")
    prs = []
    for s in range(a.seeds):
        o = oof[s]
        pr = average_precision_score(y, o)
        prs.append(pr)
        print(f"{s:>5}  {pr:8.4f}  {roc_auc_score(y, o):8.4f}")
    print(f"{'mean':>5}  {np.mean(prs):8.4f}")
    print(f"{'sd':>5}  {np.std(prs):8.4f}   <- across seeds alone, same data")

    print(f"\ntrain PR-AUC {np.mean(tr_scores):.4f} vs out-of-fold {np.mean(prs):.4f}"
          f"  gap {np.mean(tr_scores)-np.mean(prs):+.4f}")
    print("  " + ("-> memorising" if np.mean(tr_scores)-np.mean(prs) > 0.25
                  else "-> train and out-of-fold are close"))
    d_ = np.mean(prs) - a.baseline
    print(f"\nbaseline (trees, tabular features): {a.baseline:.4f}")
    print(f"CNN minus trees: {d_:+.4f}, seed spread {np.std(prs):.4f}")
    print("  " + ("gap is inside the seed spread -- not established."
                  if abs(d_) < np.std(prs) else
                  ("the CNN is ahead." if d_ > 0 else "the trees are ahead.")))


if __name__ == "__main__":
    main()
