#!/usr/bin/env python3
"""
generate_pdf.py — Concise, visual, 2-3 page sentiment brief.

Design goals:
- Max 3 pages (cover + 2 category pages)
- 12pt body font minimum
- Visual sentiment gauges (TikZ bar)
- One insight per section, no walls of text
- Colour-coded, to the point
"""

import json, subprocess, sys, os, argparse, shutil
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(__file__).parent.parent
LATEX_SKILL = Path.home() / '.claude/skills/latex-document'


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


def esc(text: str) -> str:
    if not text:
        return ''
    text = str(text)
    for char, escaped in [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'), ('%', r'\%'), ('$', r'\$'), ('#', r'\#'),
        ('^', r'\^{}'), ('_', r'\_'), ('{', r'\{'), ('}', r'\}'),
        ('~', r'\textasciitilde{}'), ('<', r'\textless{}'), ('>', r'\textgreater{}'),
    ]:
        text = text.replace(char, escaped)
    return text


def score_color(score: int) -> str:
    if score >= 4:   return 'accentgreen'
    elif score >= 0: return 'accentorange'
    return 'accentred'


def score_word(score: int) -> str:
    if score >= 7:   return 'Very Positive'
    if score >= 4:   return 'Optimistic'
    if score >= 1:   return 'Cautiously Positive'
    if score == 0:   return 'Neutral'
    if score >= -3:  return 'Slightly Negative'
    if score >= -6:  return 'Negative'
    return 'Very Negative'


def fmt_score(score: int) -> str:
    return f'+{score}' if score >= 0 else str(score)


def sentiment_bar(score: int) -> str:
    """Generate a TikZ horizontal bar showing score from -10 to +10."""
    # score is -10 to +10
    # bar shows -10 to +10, score position marked
    norm = (score + 10) / 20  # 0 to 1
    bar_color = score_color(score)
    score_str = fmt_score(score)
    label = score_word(score)

    return (
        r'\begin{tikzpicture}[baseline=0pt, scale=1.8]' '\n'
        r'  \fill[lightgray] (0,0) rectangle (5,0.18);' '\n'
        r'  \fill[' + bar_color + r'] (0,0) rectangle (' + f'{5*norm:.3f}' + r',0.18);' '\n'
        r'  \draw[thick] (0,0) -- (5,0);' '\n'
        r'  \node[anchor=south west] at (0,-0.02) {\LARGE\bfseries ' + score_str + r'/10};' '\n'
        r'  \node[anchor=south east] at (5,-0.02) {' + esc(label) + r'};' '\n'
        r'\end{tikzpicture}'
    )


def build_preamble() -> str:
    return (
        r'\documentclass[12pt,a4paper]{article}' '\n'
        r'\usepackage[utf8]{inputenc}' '\n'
        r'\usepackage[T1]{fontenc}' '\n'
        r'\usepackage[margin=1.8cm, top=2cm, bottom=2cm]{geometry}' '\n'
        r'\usepackage{xcolor}' '\n'
        r'\usepackage{titlesec}' '\n'
        r'\usepackage{parskip}' '\n'
        r'\usepackage{booktabs}' '\n'
        r'\usepackage{tabularx}' '\n'
        r'\usepackage{enumitem}' '\n'
        r'\usepackage{fancyhdr}' '\n'
        r'\usepackage{tikz}' '\n'
        r'\usepackage[protrusion=true,expansion=false]{microtype}' '\n'
        r'\usepackage{hyperref}' '\n'
        r'\hypersetup{colorlinks=false, pdfborder={0 0 0}}' '\n'
        '\n'
        r'\definecolor{deepblue}{HTML}{1A2B4C}' '\n'
        r'\definecolor{accentred}{HTML}{C0392B}' '\n'
        r'\definecolor{accentgreen}{HTML}{27AE60}' '\n'
        r'\definecolor{accentorange}{HTML}{E67E22}' '\n'
        r'\definecolor{lightgray}{HTML}{DDDDDD}' '\n'
        r'\definecolor{midgray}{HTML}{AAAAAA}' '\n'
        r'\definecolor{darkgray}{HTML}{444444}' '\n'
        '\n'
        r'\titleformat{\section}{\Large\bfseries\color{deepblue}}{}{0em}{}' '\n'
        r'\titlespacing{\section}{0pt}{16pt}{8pt}' '\n'
        r'\titlespacing\subsection{0pt}{10pt}{4pt}' '\n'
        '\n'
        r'\pagestyle{fancy}' '\n'
        r'\fancyhf{}' '\n'
        r'\fancyhead[L]{\small\color{darkgray}Reddit Daily Brief}' '\n'
        r'\fancyhead[R]{\small\color{darkgray}\date}' '\n'
        r'\fancyfoot[C]{\small\color{midgray}\thepage}' '\n'
        r'\fancyfoot[R]{\small\color{midgray}\leftmark}' '\n'
        '\n'
        r'\setlist[itemize]{leftmargin=1.5em, itemsep=2pt, topsep=2pt}' '\n'
        '\n'
        r'\begin{document}'
        '\n'
        r'\date{}'
    )


def build_page1(date_str: str, overall: dict, categories: list) -> str:
    composite = overall.get('composite_score', 0)
    signals = overall.get('macro_signals', [])
    summary = overall.get('overall_summary', '')
    num_subs = sum(len(c.get('subreddits', [])) for c in categories)

    # Overall bar
    overall_bar = sentiment_bar(composite)

    # Category summary table
    rows = []
    for cat in categories:
        score = cat.get('sentiment_score', 0)
        color = score_color(score)
        mood = esc(cat.get('dominant_mood', '')[:60])
        name = esc(cat.get('name', ''))
        s_str = fmt_score(score)
        rows.append(
            f'{name} & {mood} & '
            f'\\textcolor{{{color}}}{{\\textbf{{{s_str}}}}}'
        )

    rows_tex = ' \\\\\n'.join(rows) + ' \\\\'

    lines = [
        r'%% PAGE 1 — COVER',
        r'\thispagestyle{empty}',
        r'\vspace*{0.5cm}',
        r'{\color{deepblue}\Huge\textbf{Reddit Daily Brief}}\\[0.4cm]',
        r'{\LARGE\color{darkgray}' + esc(date_str) + r' \quad|\quad ' + str(num_subs) + r' subreddits}\\[1cm]',
        r'\section*{Overall Sentiment}',
        overall_bar,
        r'\\[0.4cm]',
    ]

    if summary:
        lines.append(r'{\large\itshape ' + esc(summary[:200]) + r'}')
        lines.append(r'\\[0.6cm]')

    # Key signals
    if signals:
        lines += [
            r'\section*{Key Signals}',
            r'\begin{tabularx}{\textwidth}{p{0.4cm}X}',
        ]
        for i, sig in enumerate(signals[:4], 1):
            color = score_color(0)  # neutral for signals
            lines.append(r'\textbf{' + str(i) + r'.} & ' + esc(sig[:120]) + r' \\')
        lines.append(r'\end{tabularx}')
        lines.append(r'\\[0.5cm]')

    # Category snapshot table
    lines += [
        r'\section*{Category Snapshot}',
        r'\begin{tabularx}{\textwidth}{p{4cm} p{7cm} r}',
        r'\toprule',
        r'\textbf{Category} & \textbf{Mood} & \textbf{Score} \\',
        r'\midrule',
        rows_tex,
        r'\bottomrule',
        r'\end{tabularx}',
    ]

    lines.append(r'\newpage')
    return '\n'.join(lines)


def build_cat_page(cat: dict, page_num: int) -> str:
    name = cat.get('name', 'Unknown')
    score = cat.get('sentiment_score', 0)
    discussions = cat.get('top_discussions', [])
    frustrations = cat.get('key_frustrations', [])
    positives = cat.get('positive_signals', [])
    viral = cat.get('viral_thread', '')
    controversy = cat.get('controversy', '')

    color = score_color(score)
    score_str = fmt_score(score)
    label = score_word(score)
    subs_str = esc(', '.join(f'r/{s}' for s in cat.get('subreddits', [])))
    post_count = cat.get('post_count', 0)

    lines = [
        r'%% PAGE ' + str(page_num) + ' — ' + esc(name),
        r'\section*{' + esc(name) + r'}',
        r'{\color{' + color + r'}\textbf{' + score_str + r'/10 — ' + esc(label) + r'}} \quad ' + esc(subs_str) + r' \quad (' + str(post_count) + r' posts)',
        r'\\[0.4cm]',
        sentiment_bar(score),
        r'\\[0.5cm]',
    ]

    # Top discussions — concise, one line each
    if discussions:
        lines.append(r'\subsection*{Top Discussions}')
        for d in discussions[:3]:
            lines.append(r'\textbf{\textbullet\ ' + esc(str(d)[:150]) + r'}')
            lines.append(r'\\[0.25cm]')

    # Frustrations — brief
    if frustrations:
        lines.append(r'\subsection*{Frustrations}')
        for f in frustrations[:2]:
            lines.append(r'\textbf{\textbullet\ ' + esc(str(f)[:150]) + r'}')
            lines.append(r'\\[0.2cm]')

    # Positives — brief
    if positives:
        lines.append(r'\subsection*{Positives}')
        for p in positives[:2]:
            lines.append(r'\textbf{\textbullet\ ' + esc(str(p)[:150]) + r'}')
            lines.append(r'\\[0.2cm]')

    # Viral thread
    if viral:
        lines.append(r'\subsection*{Viral}')
        lines.append(r'\textit{' + esc(str(viral)[:200]) + r'}')
        lines.append(r'\\[0.3cm]')

    # Controversy
    if controversy:
        lines.append(r'\subsection*{Controversy}')
        lines.append(r'\textit{' + esc(str(controversy)[:180]) + r'}')

    lines.append(r'\newpage')
    return '\n'.join(lines)


def build_latex(cfg: dict, date_str: str, qa_data: dict) -> str:
    overall = {
        'composite_score': qa_data.get('composite_score', 0),
        'macro_signals': qa_data.get('macro_signals', []),
        'overall_summary': qa_data.get('overall_summary', ''),
    }
    categories = qa_data.get('categories', [])

    parts = [build_preamble(), build_page1(date_str, overall, categories)]

    for i, cat in enumerate(categories, 2):
        parts.append(build_cat_page(cat, i))

    doc = '\n'.join(parts)
    tail = doc.rstrip()
    if tail.endswith(r'\newpage'):
        doc = tail[:-len(r'\newpage')].rstrip() + '\n'
    doc += '\n\\end{document}\n'
    return doc


def compile_latex(tex_content: str, output_path: Path) -> bool:
    tex_path = output_path.with_suffix('.tex')
    tex_path.write_text(tex_content, encoding='utf-8')
    print(f'  LaTeX: {tex_path}')

    compile_script = LATEX_SKILL / 'scripts/compile_latex.sh'
    if not compile_script.exists():
        tinytex = Path.home() / '.TinyTeX/bin/x86_64-linux/pdflatex'
        pdflatex = str(tinytex) if tinytex.exists() else (shutil.which('pdflatex') or 'pdflatex')
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            if tinytex.parent.exists():
                env['PATH'] = str(tinytex.parent) + ':' + env.get('PATH', '')
            for _ in range(2):
                subprocess.run(
                    [pdflatex, '-interaction=nonstopmode', '-output-directory', tmpdir, str(tex_path)],
                    capture_output=True, text=True, timeout=90, env=env
                )
            pdf_tmp = Path(tmpdir) / (tex_path.stem + '.pdf')
            if pdf_tmp.exists():
                shutil.copy2(pdf_tmp, output_path)
                return True
        return False

    env = os.environ.copy()
    tinytex_dir = Path.home() / '.TinyTeX/bin/x86_64-linux'
    if tinytex_dir.exists():
        env['PATH'] = str(tinytex_dir) + ':' + env.get('PATH', '')

    result = subprocess.run(
        ['bash', str(compile_script), str(tex_path)],
        env=env, capture_output=False, text=True, timeout=120,
        cwd=str(tex_path.parent)
    )

    expected_pdf = tex_path.with_suffix('.pdf')
    if expected_pdf.exists():
        if str(expected_pdf) != str(output_path):
            shutil.copy2(expected_pdf, output_path)
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=None)
    parser.add_argument('--date', default=None)
    parser.add_argument('--qa-file', default=None)
    parser.add_argument('--daily-dir', default=None)
    parser.add_argument('--output', default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    date_str = args.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')

    composed_dir = SKILL_DIR / 'outputs/composed'
    qa_file = Path(args.qa_file) if args.qa_file else composed_dir / f'qa_{date_str}.json'

    if not qa_file.exists():
        print(f'ERROR: Q&A file not found: {qa_file}')
        print('Run query_compose.py first.')
        sys.exit(1)

    with open(qa_file) as f:
        qa_data = json.load(f)

    pdf_dir = os.path.expanduser(
        cfg.get('pdf', {}).get('output_dir', str(SKILL_DIR / 'outputs/pdfs'))
    )
    Path(pdf_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else Path(pdf_dir) / f'reddit-brief-{date_str}.pdf'

    print(f'=== Generate PDF — {date_str} ===')

    tex = build_latex(cfg, date_str, qa_data)
    ok = compile_latex(tex, output_path)

    if ok:
        size_kb = output_path.stat().st_size // 1024
        print(f'  PDF: {output_path}  ({size_kb}KB)')
    else:
        tex_path = output_path.with_suffix('.tex')
        print(f'  [ERROR] PDF failed. LaTeX at: {tex_path}')
        sys.exit(1)

    print('=== PDF complete ===')


if __name__ == '__main__':
    main()