"""Shared LaTeX components used by every document profile and workspace."""

from wood_reports.branding import parse_logo
from wood_reports.model import Report
from wood_reports.primitives import latex_escape


def latex_preamble(report: Report) -> list[str]:
    theme = report.theme
    geometry = theme.geometry
    typography = theme.typography
    table_stretch = max(1, theme.table_layout.row_inches * 72 / (typography.table + 2))
    confidentiality_slot = "C" if theme.branding.corner == "bottom-left" else "L"
    page_slot = "C" if theme.branding.corner == "bottom-right" else "R"
    parts = [
        f"\\documentclass[{typography.page_body}pt]{{article}}",
        r"\usepackage{graphicx,booktabs,longtable}",
        r"\usepackage[table]{xcolor}",
        r"\usepackage{geometry,fancyhdr,caption,titlesec,iftex}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{tikz,eso-pic}",
        r"\usepackage{needspace,ragged2e}",
        f"\\geometry{{paperwidth={geometry.page_width}in,"
        f"paperheight={geometry.page_height}in,"
        f"margin={geometry.page_margin}in,headheight=15pt}}",
        r"\ifPDFTeX",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{helvet}",
        r"\renewcommand{\familydefault}{\sfdefault}",
        r"\else",
        r"\usepackage{fontspec}",
        r"\IfFontExistsTF{"
        + latex_escape(typography.family)
        + r"}{\setsansfont{"
        + latex_escape(typography.family)
        + r"}}{\IfFontExistsTF{"
        + latex_escape(typography.fallback)
        + r"}{\setsansfont{"
        + latex_escape(typography.fallback)
        + r"}}{\setsansfont{lmsans10-regular.otf}}}",
        r"\IfFontExistsTF{"
        + latex_escape(typography.code_family)
        + r"}{\setmonofont{"
        + latex_escape(typography.code_family)
        + r"}}{\setmonofont{lmmono10-regular.otf}}",
        r"\renewcommand{\familydefault}{\sfdefault}",
        r"\fi",
    ]
    parts.extend(
        f"\\definecolor{{Wood{name}}}{{HTML}}{{{getattr(theme.colors, name)[1:]}}}"
        for name in (
            "primary",
            "secondary",
            "text_primary",
            "text_muted",
            "grid",
            "background",
            "warning",
            "critical",
        )
    )
    parts.extend(
        [
            r"\color{Woodtext_primary}",
            r"\pagecolor{Woodbackground}",
            f"\\setlength{{\\parskip}}{{{theme.spacing.paragraph_points}pt}}",
            r"\setlength{\parindent}{0pt}",
            r"\pagestyle{fancy}\fancyhf{}",
            r"\renewcommand{\headrulewidth}{0pt}",
            "\\fancyfoot["
            + confidentiality_slot
            + r"]{\small\color{Woodtext_muted} "
            + latex_escape(report.metadata.confidentiality or "")
            + "}",
            "\\fancyfoot[" + page_slot + r"]{\small\thepage}"
            if theme.page_numbers
            else "\\fancyfoot[" + page_slot + "]{}",
            r"\fancypagestyle{plain}{\fancyhf{}"
            + "\\fancyfoot["
            + confidentiality_slot
            + r"]{\small\color{Woodtext_muted} "
            + latex_escape(report.metadata.confidentiality or "")
            + "}"
            + (
                "\\fancyfoot[" + page_slot + r"]{\thepage}"
                if theme.page_numbers
                else ""
            )
            + "}",
            r"\titleformat{\section}{\color{Woodprimary}\sffamily\bfseries"
            + f"\\fontsize{{{typography.page_heading}}}"
            + f"{{{typography.page_heading + 3}}}"
            + r"\selectfont}{\thesection}{1em}{}",
            r"\titleformat{\subsection}{\color{Woodprimary}\sffamily\bfseries}"
            r"{\thesubsection}{1em}{}",
            r"\DeclareCaptionFont{woodcaption}{"
            + f"\\fontsize{{{typography.caption}}}{{{typography.caption + 2}}}"
            + r"\selectfont\color{Woodtext_muted}}",
            r"\captionsetup{font=woodcaption,labelfont=bf}",
            r"\newcommand{\WoodTableFont}{"
            + f"\\fontsize{{{typography.table}}}{{{typography.table + 2}}}"
            + r"\selectfont}",
            r"\newcommand{\WoodNoteFont}{"
            + f"\\fontsize{{{typography.note}}}{{{typography.note + 2}}}"
            + r"\selectfont}",
            r"\newcommand{\WoodTableSetup}{\renewcommand{\arraystretch}{"
            + f"{table_stretch:.5f}"
            + "}}",
            # longtable gh/1907: finite shrink in the page-output box, scoped
            # to this environment. Do not change engine diagnostic controls.
            r"\AddToHook{env/longtable/begin}{"
            r"\def\vss{\vskip0pt plus1fil minus\normalbaselineskip}}",
            r"\newsavebox{\WoodTableStart}",
            r"\newcommand{\WoodTableSpace}{\par"
            r"\ifdim\dimexpr\ht\WoodTableStart+\dp\WoodTableStart"
            r"+2\baselineskip+\LTpre\relax<\textheight"
            r"\def\WoodProtectedRowEnd{\\*}\Needspace{"
            r"\dimexpr\ht\WoodTableStart+\dp\WoodTableStart"
            r"+2\baselineskip+\LTpre\relax}"
            r"\else\def\WoodProtectedRowEnd{\\}"
            r"\PackageWarning{wood-reports}{Table start group exceeds page;"
            r" row grouping relaxed}\fi}",
            r"\newenvironment{WoodTechnicalParagraph}{\par\begingroup"
            r"\RaggedRight}{\par\endgroup}",
            r"\newcommand{\WoodSource}[1]{\par{\WoodNoteFont\color{Woodtext_muted}"
            r"\textit{Source: #1}}\par}",
            r"\newcommand{\WoodConfidentiality}[1]{\par{\small\bfseries #1}\par}",
            r"\newcommand{\WoodCallout}[3]{\par\noindent"
            r"\fcolorbox{#1}{Woodbackground}{\parbox{"
            r"\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{"
            r"\color{#1}\textbf{#2}\par\color{Woodtext_primary}#3}}\par}",
        ]
    )
    parts.extend(font_validation(report))
    parts.extend(brand_components(report))
    return parts


def font_validation(report: Report) -> list[str]:
    """Validate on the compiler host, where actual font selection happens."""
    strict = report.theme.branding.font_policy == "strict"
    command = "PackageError" if strict else "PackageWarning"
    lines = [r"\ifPDFTeX"]
    if strict:
        lines.append(
            r"\PackageError{wood-reports}{Strict fonts require LuaLaTeX or XeLaTeX}"
            r"{Use the declared workspace engine}"
        )
    lines.append(r"\else")
    for family in (report.theme.typography.family, report.theme.typography.code_family):
        message = f"Font unavailable: {latex_escape(family)}"
        failure = f"\\{command}{{wood-reports}}{{{message}}}"
        if strict:
            failure += "{Install the required font or select fallback policy}"
        lines.append(f"\\IfFontExistsTF{{{latex_escape(family)}}}{{}}{{{failure}}}")
    lines.append(r"\fi")
    return lines


def brand_components(report: Report) -> list[str]:
    theme = report.theme
    branding = theme.branding
    logo = parse_logo(theme.wordmark_svg)
    scale = min(branding.width / logo.width, branding.height / logo.height)
    x, y = branding.position(theme.geometry.page_width, theme.geometry.page_height)
    lines = [
        r"\newcommand{\WoodBrandLogo}{%",
        f"\\begin{{tikzpicture}}[x={scale:.8f}in,y=-{scale:.8f}in]",
        f"\\path[use as bounding box] (0,0) rectangle ({logo.width},{logo.height});",
    ]
    for index, shape in enumerate(logo.shapes):
        color = f"WoodLogo{index}"
        lines.append(f"\\definecolor{{{color}}}{{HTML}}{{{shape.color[1:]}}}")
        if shape.text:
            point = shape.contours[0][0]
            size = shape.font_size * scale * 72.27
            weight = r"\bfseries" if shape.bold else ""
            lines.append(
                f"\\node[anchor=base west,inner sep=0pt,text={color},"
                f"font=\\sffamily{weight}\\fontsize{{{size:.5f}}}"
                f"{{{size * 1.2:.5f}}}\\selectfont] "
                f"at ({point.real},{point.imag}) {{{latex_escape(shape.text)}}};"
            )
        else:
            paths = [
                " -- ".join(f"({p.real:.5f},{p.imag:.5f})" for p in contour)
                + " -- cycle"
                for contour in shape.contours
            ]
            lines.append(f"\\path[fill={color},nonzero rule] " + " ".join(paths) + ";")
    lines.extend([r"\end{tikzpicture}%", "}"])
    overlay = (
        r"\begin{tikzpicture}[remember picture,overlay]"
        f"\\node[anchor=north west,inner sep=0pt] at "
        f"([xshift={x}in,yshift=-{y}in]current page.north west)"
        r"{\WoodBrandLogo};\end{tikzpicture}"
    )
    lines.append(
        r"\AddToShipoutPictureFG{\ifnum\value{page}=1 "
        + (overlay if branding.cover_visible else "")
        + r"\else "
        + (overlay if branding.visible else "")
        + r"\fi}"
    )
    return lines
