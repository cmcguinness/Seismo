# Papers kept in the repo

Originals that are tens of megabytes (vector figures with hundreds of thousands of
points) are **not committed** — `doc/.gitignore` lists them. What is committed is a
150 dpi rasterised copy (readable, ~4 MB) and a `pdftotext` extract for grep.

| paper | committed | original | DOI |
|---|---|---|---|
| Yeck et al. 2020, *Leveraging Deep Learning in Global 24/7 Real-Time Earthquake Monitoring at the NEIC*, SRL | `yeck2020-150dpi.pdf`, `yeck2020.txt` | `yeck2020.pdf` (58 MB, local only) | 10.1785/0220200178 |

Regenerate: `gs -q -sDEVICE=pdfimage24 -r150 -dNOPAUSE -dBATCH -sOutputFile=X-150dpi.pdf X.pdf`
and `pdftotext -layout X.pdf X.txt`. (`-dPDFSETTINGS` downsampling does nothing here —
the bulk is vector paths, not images — it made the file larger.)
