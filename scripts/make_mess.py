"""Create a realistic messy folder for the live demo.

Usage:  python scripts/make_mess.py demo_mess --count 1200
Files are tiny text placeholders with realistic names and dates.
"""
from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path

KINDS = {
    "screenshot": (0.20, lambda r: f"Screenshot 2026-{r.randint(1,10):02d}-{r.randint(1,28):02d} at {r.randint(0,23):02d}.{r.randint(0,59):02d}.{r.randint(0,59):02d}.png"),
    "invoice": (0.08, lambda r: f"{r.choice(['invoice','Invoice','receipt','Amazon_receipt','electricity_bill','payment_confirmation','Swiggy_receipt'])}_{r.randint(1000,99999)}.pdf"),
    "resume": (0.02, lambda r: f"{r.choice(['resume','Resume_Vedansh','CV','resume_final','resume_FINAL_v','cover_letter'])}{r.randint(1,30)}.{r.choice(['pdf','docx'])}"),
    "installer": (0.04, lambda r: f"{r.choice(['ChromeSetup','vscode-installer','zoom_x64','python-3.12.','Discord_Setup','node-v22.','AnyDesk','WhatsAppSetup'])}{r.randint(1,99)}.{r.choice(['exe','msi','dmg'])}"),
    "duplicate": (0.07, lambda r: f"{r.choice(['notes','report','lab_manual','IMG_4421','assignment','DSA_sheet'])}{r.randint(1,40)}{r.choice([' (1)',' (2)','_copy',' copy'])}.{r.choice(['pdf','jpg','docx'])}"),
    "image": (0.16, lambda r: f"{r.choice(['IMG_','DSC_','WhatsApp Image 2026-'])}{r.randint(1000,99999)}.{r.choice(['jpg','jpeg','png','heic'])}"),
    "pdf": (0.12, lambda r: f"{r.choice(['DBMS_unit','lecture','OS_notes','paper','syllabus','ticket','boarding_pass','CN_assignment'])}_{r.randint(1,999)}.pdf"),
    "doc": (0.07, lambda r: f"{r.choice(['notes','todo','ideas','minutes','draft','essay'])}_{r.randint(1,999)}.{r.choice(['txt','docx','md'])}"),
    "sheet": (0.04, lambda r: f"{r.choice(['marks','budget','attendance','data','expenses'])}_{r.randint(1,999)}.{r.choice(['xlsx','csv'])}"),
    "archive": (0.04, lambda r: f"{r.choice(['project','dataset','photos','backup','submission'])}_{r.randint(1,999)}.zip"),
    "code": (0.03, lambda r: f"{r.choice(['main','test','solution','scraper','app','lc'])}_{r.randint(1,999)}.{r.choice(['py','js','cpp','ipynb'])}"),
    "slides": (0.02, lambda r: f"{r.choice(['pitch','ppt_final','seminar','review'])}_{r.randint(1,99)}.pptx"),
    "video": (0.02, lambda r: f"VID_{r.randint(1000,99999)}.mp4"),
    "audio": (0.02, lambda r: f"{r.choice(['voice_note','recording','song'])}_{r.randint(1,999)}.{r.choice(['mp3','m4a'])}"),
    "random": (0.07, lambda r: f"{r.choice(['untitled','download','file','New document','asdf'])}{r.randint(1,999)}{r.choice(['','.bin','.dat','.tmp'])}"),
}


def make(out: Path, count: int, seed: int) -> int:
    r = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    names, weights = zip(*[(k, v[0]) for k, v in KINDS.items()])
    made = 0
    now = time.time()
    attempts = 0
    while made < count and attempts < count * 5:
        attempts += 1
        kind = r.choices(names, weights)[0]
        name = KINDS[kind][1](r)
        path = out / name
        if path.exists():
            continue
        path.write_text(f"ChoreRaid demo file ({kind}): {name}\n", encoding="utf-8")
        t = now - r.randint(0, 300) * 86400
        os.utime(path, (t, t))
        made += 1
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="demo_mess")
    ap.add_argument("--count", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    n = make(Path(a.out), a.count, a.seed)
    print(f"Created {n} messy files in {a.out}/")
