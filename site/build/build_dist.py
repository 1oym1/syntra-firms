"""Makes site/dist/: a standalone copy of the story page for any static host (Netlify, GitHub Pages).
site/index.html is written for claude.ai artifacts (no <html> wrapper); this adds the doctype and wrapper.
    python site/build/build_dist.py
"""
import pathlib, shutil
site = pathlib.Path(__file__).resolve().parents[1]
dist = site / "dist"
dist.mkdir(exist_ok=True)
page = (site / "index.html").read_text(encoding="utf-8")
(dist / "index.html").write_text('<!doctype html>\n<html lang="en">\n' + page + "\n</html>\n", encoding="utf-8")
shutil.copy(site / "data.js", dist / "data.js")
if (site / "team").is_dir():                       # team photos
    shutil.copytree(site / "team", dist / "team", dirs_exist_ok=True)
print("built", dist, [p.name for p in dist.iterdir()])
