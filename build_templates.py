#!/usr/bin/env python3
"""
build_templates.py - templates for Right-Click New (the Windows "New" menu for Linux).

GNOME Files (Nautilus) and Ubuntu's desktop icons build the right-click
"New Document" submenu from the files in your XDG Templates folder
(usually ~/Templates). Each file's name, minus its extension, becomes the
menu label. This script fills that folder with *valid* blank documents,
labelled the way Windows labels its New menu.

Standard library only (Python 3.8+), so it runs on a stock Ubuntu install.

Usage
    python3 build_templates.py install   [--no-extras] [--group-extras]
                                         [--paper {letter,a4}]
                                         [--bitmap-size WxH] [--force]
    python3 build_templates.py uninstall [--force]
    python3 build_templates.py list
    python3 build_templates.py build OUT_DIR   # write files only, no manifest

Safety
    * Only files this script wrote are ever updated or removed. A file you
      edited, or one that was already there, is left alone unless --force,
      and --force first copies it to ~/.local/share/right-click-new/backup/.
    * A manifest of what was installed lives in
      ~/.local/share/right-click-new/manifest.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

APP_NAME = "right-click-new"
MANIFEST_VERSION = 1
EXTRAS_FOLDER = "Code and Data"


# --------------------------------------------------------------------------
# Options and template registry
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Options:
    paper: str = "letter"                       # "letter" or "a4"
    bitmap_size: Tuple[int, int] = (1920, 1080)


@dataclass(frozen=True)
class Template:
    filename: str                               # also the menu label source
    group: str                                  # "windows" or "extras"
    build: Callable[[Options], bytes]
    note: str

    @property
    def label(self) -> str:
        return self.filename.rsplit(".", 1)[0]


# --------------------------------------------------------------------------
# Office Open XML helpers
# --------------------------------------------------------------------------

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_PKG_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

REL_DOC = NS_R + "/officeDocument"
REL_CORE = NS_PKG_RELS + "/metadata/core-properties"

CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_CORE = "application/vnd.openxmlformats-package.core-properties+xml"
OOXML = "application/vnd.openxmlformats-officedocument"

# Fixed timestamp so the same options always produce byte-identical files.
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _zip(parts: List[Tuple[str, str]]) -> bytes:
    """Build an OPC package. [Content_Types].xml must come first."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def _content_types(overrides: List[Tuple[str, str]]) -> str:
    rows = "".join(
        f'<Override PartName="{part}" ContentType="{ctype}"/>'
        for part, ctype in overrides
    )
    return (
        f'{XML_DECL}<Types xmlns="{NS_CT}">'
        f'<Default Extension="rels" ContentType="{CT_RELS}"/>'
        f'<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/docProps/core.xml" ContentType="{CT_CORE}"/>'
        f"{rows}</Types>"
    )


def _rels(rels: List[Tuple[str, str, str]]) -> str:
    rows = "".join(
        f'<Relationship Id="{rid}" Type="{rtype}" Target="{target}"/>'
        for rid, rtype, target in rels
    )
    return f'{XML_DECL}<Relationships xmlns="{NS_PKG_RELS}">{rows}</Relationships>'


def _package_rels(main_part: str) -> str:
    return _rels([
        ("rId1", REL_DOC, main_part),
        ("rId2", REL_CORE, "docProps/core.xml"),
    ])


CORE_PROPS = (
    f"{XML_DECL}<cp:coreProperties "
    'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
)


# --------------------------------------------------------------------------
# Microsoft Word Document (.docx)
# --------------------------------------------------------------------------

PAPER_TWIPS = {"letter": (12240, 15840), "a4": (11906, 16838)}


def build_docx(opts: Options) -> bytes:
    width, height = PAPER_TWIPS[opts.paper]
    document = (
        f'{XML_DECL}<w:document xmlns:w="{NS_W}" xmlns:r="{NS_R}"><w:body>'
        "<w:p/>"
        "<w:sectPr>"
        f'<w:pgSz w:w="{width}" w:h="{height}"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/>'
        "</w:sectPr></w:body></w:document>"
    )
    styles = (
        f'{XML_DECL}<w:styles xmlns:w="{NS_W}">'
        "<w:docDefaults>"
        "<w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="Calibri" w:eastAsia="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
        '<w:sz w:val="22"/><w:szCs w:val="22"/>'
        '<w:lang w:val="en-US" w:eastAsia="en-US" w:bidi="ar-SA"/>'
        "</w:rPr></w:rPrDefault>"
        '<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault>"
        "</w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>'
        '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont">'
        '<w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/>'
        "<w:semiHidden/><w:unhideWhenUsed/></w:style>"
        '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
        '<w:name w:val="Normal Table"/><w:uiPriority w:val="99"/>'
        "<w:semiHidden/><w:unhideWhenUsed/>"
        '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar>'
        '<w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
        '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
        "</w:tblCellMar></w:tblPr></w:style>"
        '<w:style w:type="numbering" w:default="1" w:styleId="NoList">'
        '<w:name w:val="No List"/><w:uiPriority w:val="99"/>'
        "<w:semiHidden/><w:unhideWhenUsed/></w:style>"
        "</w:styles>"
    )
    # compatibilityMode 15 stops Word from opening the file in
    # "Compatibility Mode".
    settings = (
        f'{XML_DECL}<w:settings xmlns:w="{NS_W}">'
        '<w:defaultTabStop w:val="720"/>'
        '<w:characterSpacingControl w:val="doNotCompress"/>'
        "<w:compat>"
        '<w:compatSetting w:name="compatibilityMode" '
        'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
        "</w:compat></w:settings>"
    )
    wml = OOXML + ".wordprocessingml"
    return _zip([
        ("[Content_Types].xml", _content_types([
            ("/word/document.xml", wml + ".document.main+xml"),
            ("/word/styles.xml", wml + ".styles+xml"),
            ("/word/settings.xml", wml + ".settings+xml"),
        ])),
        ("_rels/.rels", _package_rels("word/document.xml")),
        ("docProps/core.xml", CORE_PROPS),
        ("word/document.xml", document),
        ("word/_rels/document.xml.rels", _rels([
            ("rId1", NS_R + "/styles", "styles.xml"),
            ("rId2", NS_R + "/settings", "settings.xml"),
        ])),
        ("word/styles.xml", styles),
        ("word/settings.xml", settings),
    ])


# --------------------------------------------------------------------------
# Microsoft Excel Worksheet (.xlsx)
# --------------------------------------------------------------------------

def build_xlsx(opts: Options) -> bytes:
    workbook = (
        f'{XML_DECL}<workbook xmlns="{NS_S}" xmlns:r="{NS_R}">'
        "<bookViews><workbookView/></bookViews>"
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    sheet = (
        f'{XML_DECL}<worksheet xmlns="{NS_S}" xmlns:r="{NS_R}">'
        '<dimension ref="A1"/>'
        '<sheetViews><sheetView tabSelected="1" workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        "<sheetData/>"
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" '
        'header="0.3" footer="0.3"/>'
        "</worksheet>"
    )
    styles = (
        f'{XML_DECL}<styleSheet xmlns="{NS_S}">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/>'
        '<family val="2"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/>'
        "</border></borders>"
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
        "</cellStyles>"
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" '
        'defaultPivotStyle="PivotStyleLight16"/>'
        "</styleSheet>"
    )
    sml = OOXML + ".spreadsheetml"
    return _zip([
        ("[Content_Types].xml", _content_types([
            ("/xl/workbook.xml", sml + ".sheet.main+xml"),
            ("/xl/worksheets/sheet1.xml", sml + ".worksheet+xml"),
            ("/xl/styles.xml", sml + ".styles+xml"),
        ])),
        ("_rels/.rels", _package_rels("xl/workbook.xml")),
        ("docProps/core.xml", CORE_PROPS),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", _rels([
            ("rId1", NS_R + "/worksheet", "worksheets/sheet1.xml"),
            ("rId2", NS_R + "/styles", "styles.xml"),
        ])),
        ("xl/worksheets/sheet1.xml", sheet),
        ("xl/styles.xml", styles),
    ])


# --------------------------------------------------------------------------
# Microsoft PowerPoint Presentation (.pptx)
# One 16:9 title slide; layouts: Title Slide, Title and Content,
# Title Only, Blank (so "New Slide" behaves as expected).
# --------------------------------------------------------------------------

_PML_NS = f'xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}"'

_GROUP_HEADER = (
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
)

_FONT_REFS = {
    "mj": '<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/><a:cs typeface="+mj-cs"/>',
    "mn": '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/>',
}
_TX1 = '<a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
_PPR_COMMON = 'defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1"'


def _placeholder(shape_id: int, name: str, ph: str,
                 xfrm: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
                 body_pr: str = "<a:bodyPr/>", lst_style: str = "<a:lstStyle/>",
                 prompt: Optional[str] = None) -> str:
    if xfrm:
        (x, y), (cx, cy) = xfrm
        sp_pr = (
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>'
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        )
    else:
        sp_pr = "<p:spPr/>"
    if prompt:
        para = (f'<a:p><a:r><a:rPr lang="en-US"/><a:t>{prompt}</a:t></a:r>'
                '<a:endParaRPr lang="en-US"/></a:p>')
    else:
        para = '<a:p><a:endParaRPr lang="en-US"/></a:p>'
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f"<p:nvPr><p:ph {ph}/></p:nvPr></p:nvSpPr>"
        f"{sp_pr}<p:txBody>{body_pr}{lst_style}{para}</p:txBody></p:sp>"
    )


def _body_level(n: int, mar_l: int, size: int, space_before: int) -> str:
    return (
        f'<a:lvl{n}pPr marL="{mar_l}" indent="-228600" algn="l" {_PPR_COMMON}>'
        '<a:lnSpc><a:spcPct val="90000"/></a:lnSpc>'
        f'<a:spcBef><a:spcPts val="{space_before}"/></a:spcBef>'
        '<a:buFont typeface="Arial" panose="020B0604020202020204" '
        'pitchFamily="34" charset="0"/><a:buChar char="&#8226;"/>'
        f'<a:defRPr sz="{size}" kern="1200">{_TX1}{_FONT_REFS["mn"]}</a:defRPr>'
        f"</a:lvl{n}pPr>"
    )


def _pptx_theme() -> str:
    colors = [
        ("dk1", '<a:sysClr val="windowText" lastClr="000000"/>'),
        ("lt1", '<a:sysClr val="window" lastClr="FFFFFF"/>'),
        ("dk2", '<a:srgbClr val="44546A"/>'),
        ("lt2", '<a:srgbClr val="E7E6E6"/>'),
        ("accent1", '<a:srgbClr val="4472C4"/>'),
        ("accent2", '<a:srgbClr val="ED7D31"/>'),
        ("accent3", '<a:srgbClr val="A5A5A5"/>'),
        ("accent4", '<a:srgbClr val="FFC000"/>'),
        ("accent5", '<a:srgbClr val="5B9BD5"/>'),
        ("accent6", '<a:srgbClr val="70AD47"/>'),
        ("hlink", '<a:srgbClr val="0563C1"/>'),
        ("folHlink", '<a:srgbClr val="954F72"/>'),
    ]
    clr = "".join(f"<a:{k}>{v}</a:{k}>" for k, v in colors)
    solid = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    lines = "".join(
        f'<a:ln w="{w}" cap="flat" cmpd="sng" algn="ctr">{solid}'
        '<a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>'
        for w in (6350, 12700, 19050)
    )
    return (
        f'{XML_DECL}<a:theme xmlns:a="{NS_A}" name="Office Theme"><a:themeElements>'
        f'<a:clrScheme name="Office">{clr}</a:clrScheme>'
        '<a:fontScheme name="Office">'
        '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/>'
        '<a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/>'
        '<a:cs typeface=""/></a:minorFont></a:fontScheme>'
        '<a:fmtScheme name="Office">'
        f"<a:fillStyleLst>{solid * 3}</a:fillStyleLst>"
        f"<a:lnStyleLst>{lines}</a:lnStyleLst>"
        "<a:effectStyleLst>"
        + "<a:effectStyle><a:effectLst/></a:effectStyle>" * 3 +
        "</a:effectStyleLst>"
        f"<a:bgFillStyleLst>{solid * 3}</a:bgFillStyleLst>"
        "</a:fmtScheme></a:themeElements>"
        "<a:objectDefaults/><a:extraClrSchemeLst/></a:theme>"
    )


_LAYOUTS = [
    # (type, name, shapes)
    ("title", "Title Slide",
     _placeholder(2, "Title 1", 'type="ctrTitle"',
                  ((1524000, 1122363), (9144000, 2387600)),
                  body_pr='<a:bodyPr anchor="b"><a:normAutofit/></a:bodyPr>',
                  lst_style='<a:lstStyle><a:lvl1pPr algn="ctr">'
                            '<a:defRPr sz="6000"/></a:lvl1pPr></a:lstStyle>',
                  prompt="Click to edit Master title style")
     + _placeholder(3, "Subtitle 2", 'type="subTitle" idx="1"',
                    ((1524000, 3602038), (9144000, 1655762)),
                    body_pr="<a:bodyPr><a:normAutofit/></a:bodyPr>",
                    lst_style='<a:lstStyle><a:lvl1pPr marL="0" indent="0" algn="ctr">'
                              '<a:buNone/><a:defRPr sz="2400"/></a:lvl1pPr></a:lstStyle>',
                    prompt="Click to edit Master subtitle style")),
    ("obj", "Title and Content",
     _placeholder(2, "Title 1", 'type="title"', prompt="Click to edit Master title style")
     + _placeholder(3, "Content Placeholder 2", 'idx="1"',
                    prompt="Click to edit Master text styles")),
    ("titleOnly", "Title Only",
     _placeholder(2, "Title 1", 'type="title"', prompt="Click to edit Master title style")),
    ("blank", "Blank", ""),
]


def build_pptx(opts: Options) -> bytes:
    pml = OOXML + ".presentationml"
    presentation = (
        f'{XML_DECL}<p:presentation {_PML_NS} saveSubsetFonts="1">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
        '<p:sldSz cx="12192000" cy="6858000"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        "</p:presentation>"
    )
    body_pr_master = ('vert="horz" lIns="91440" tIns="45720" rIns="91440" '
                      'bIns="45720" rtlCol="0"')
    master_shapes = (
        _placeholder(2, "Title Placeholder 1", 'type="title"',
                     ((838200, 365125), (10515600, 1325563)),
                     body_pr=f'<a:bodyPr {body_pr_master} anchor="ctr"><a:normAutofit/></a:bodyPr>',
                     prompt="Click to edit Master title style")
        + _placeholder(3, "Text Placeholder 2", 'type="body" idx="1"',
                       ((838200, 1825625), (10515600, 4351338)),
                       body_pr=f"<a:bodyPr {body_pr_master}><a:normAutofit/></a:bodyPr>",
                       prompt="Click to edit Master text styles")
    )
    layout_ids = "".join(
        f'<p:sldLayoutId id="{2147483649 + i}" r:id="rId{i + 1}"/>'
        for i in range(len(_LAYOUTS))
    )
    master = (
        f"{XML_DECL}<p:sldMaster {_PML_NS}><p:cSld>"
        '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
        f"<p:spTree>{_GROUP_HEADER}{master_shapes}</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
        'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
        'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        f"<p:sldLayoutIdLst>{layout_ids}</p:sldLayoutIdLst>"
        "<p:txStyles>"
        f'<p:titleStyle><a:lvl1pPr algn="l" {_PPR_COMMON}>'
        '<a:lnSpc><a:spcPct val="90000"/></a:lnSpc>'
        '<a:spcBef><a:spcPct val="0"/></a:spcBef><a:buNone/>'
        f'<a:defRPr sz="4400" kern="1200">{_TX1}{_FONT_REFS["mj"]}</a:defRPr>'
        "</a:lvl1pPr></p:titleStyle>"
        "<p:bodyStyle>"
        + _body_level(1, 228600, 2800, 1000)
        + _body_level(2, 685800, 2400, 500)
        + _body_level(3, 1143000, 2000, 500)
        + _body_level(4, 1600200, 1800, 500)
        + _body_level(5, 2057400, 1800, 500)
        + "</p:bodyStyle>"
        '<p:otherStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr>'
        f'<a:lvl1pPr marL="0" algn="l" {_PPR_COMMON}>'
        f'<a:defRPr sz="1800" kern="1200">{_TX1}{_FONT_REFS["mn"]}</a:defRPr>'
        "</a:lvl1pPr></p:otherStyle>"
        "</p:txStyles></p:sldMaster>"
    )
    slide = (
        f"{XML_DECL}<p:sld {_PML_NS}><p:cSld><p:spTree>{_GROUP_HEADER}"
        + _placeholder(2, "Title 1", 'type="ctrTitle"')
        + _placeholder(3, "Subtitle 2", 'type="subTitle" idx="1"')
        + "</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )

    overrides = [
        ("/ppt/presentation.xml", pml + ".presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", pml + ".slideMaster+xml"),
        ("/ppt/slides/slide1.xml", pml + ".slide+xml"),
        ("/ppt/theme/theme1.xml", OOXML + ".theme+xml"),
        ("/ppt/presProps.xml", pml + ".presProps+xml"),
        ("/ppt/viewProps.xml", pml + ".viewProps+xml"),
        ("/ppt/tableStyles.xml", pml + ".tableStyles+xml"),
    ]
    parts: List[Tuple[str, str]] = []
    layout_rels = []
    for i, (ltype, name, shapes) in enumerate(_LAYOUTS, start=1):
        overrides.append((f"/ppt/slideLayouts/slideLayout{i}.xml", pml + ".slideLayout+xml"))
        layout_rels.append((f"rId{i}", NS_R + "/slideLayout",
                            f"../slideLayouts/slideLayout{i}.xml"))
        parts.append((
            f"ppt/slideLayouts/slideLayout{i}.xml",
            f'{XML_DECL}<p:sldLayout {_PML_NS} type="{ltype}" preserve="1">'
            f'<p:cSld name="{name}"><p:spTree>{_GROUP_HEADER}{shapes}</p:spTree></p:cSld>'
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>",
        ))
        parts.append((
            f"ppt/slideLayouts/_rels/slideLayout{i}.xml.rels",
            _rels([("rId1", NS_R + "/slideMaster", "../slideMasters/slideMaster1.xml")]),
        ))
    theme_rid = f"rId{len(_LAYOUTS) + 1}"

    return _zip([
        ("[Content_Types].xml", _content_types(overrides)),
        ("_rels/.rels", _package_rels("ppt/presentation.xml")),
        ("docProps/core.xml", CORE_PROPS),
        ("ppt/presentation.xml", presentation),
        ("ppt/_rels/presentation.xml.rels", _rels([
            ("rId1", NS_R + "/slideMaster", "slideMasters/slideMaster1.xml"),
            ("rId2", NS_R + "/slide", "slides/slide1.xml"),
            ("rId3", NS_R + "/presProps", "presProps.xml"),
            ("rId4", NS_R + "/viewProps", "viewProps.xml"),
            ("rId5", NS_R + "/theme", "theme/theme1.xml"),
            ("rId6", NS_R + "/tableStyles", "tableStyles.xml"),
        ])),
        ("ppt/presProps.xml", f"{XML_DECL}<p:presentationPr {_PML_NS}/>"),
        ("ppt/viewProps.xml", f"{XML_DECL}<p:viewPr {_PML_NS}/>"),
        ("ppt/tableStyles.xml",
         f'{XML_DECL}<a:tblStyleLst xmlns:a="{NS_A}" '
         'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'),
        ("ppt/theme/theme1.xml", _pptx_theme()),
        ("ppt/slideMasters/slideMaster1.xml", master),
        ("ppt/slideMasters/_rels/slideMaster1.xml.rels",
         _rels(layout_rels + [(theme_rid, NS_R + "/theme", "../theme/theme1.xml")])),
        *parts,
        ("ppt/slides/slide1.xml", slide),
        ("ppt/slides/_rels/slide1.xml.rels",
         _rels([("rId1", NS_R + "/slideLayout", "../slideLayouts/slideLayout1.xml")])),
    ])


# --------------------------------------------------------------------------
# Bitmap image (.png) and SQLite Database (.sqlite3)
# --------------------------------------------------------------------------

def build_png(opts: Options) -> bytes:
    """White RGB canvas, like a new image in Paint."""
    width, height = opts.bitmap_size
    raw = (b"\x00" + b"\xff" * (3 * width)) * height   # filter 0 + RGB row

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    phys = struct.pack(">IIB", 3780, 3780, 1)               # 96 dpi
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"pHYs", phys)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build_sqlite(opts: Options) -> bytes:
    """Empty database with a real header, so it is detected as SQLite."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "blank.sqlite3")
        con = sqlite3.connect(path)
        try:
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute("CREATE TABLE _init (x)")
            con.execute("DROP TABLE _init")
            con.commit()
            con.execute("VACUUM")
        finally:
            con.close()
        return Path(path).read_bytes()


# --------------------------------------------------------------------------
# Text-based templates
# --------------------------------------------------------------------------

def _text(content: str) -> Callable[[Options], bytes]:
    data = content.encode("utf-8")
    return lambda opts: data


PYTHON_SCRIPT = '''\
#!/usr/bin/env python3
"""Describe what this script does."""


def main() -> None:
    pass


if __name__ == "__main__":
    main()
'''

R_SCRIPT = """\
#!/usr/bin/env Rscript
# Describe what this script does.

"""

QUARTO_DOC = """\
---
title: "Untitled"
format: html
---

"""

RMARKDOWN_DOC = """\
---
title: "Untitled"
output: html_document
---

"""


def build_ipynb(opts: Options) -> bytes:
    notebook = {
        "cells": [{
            "cell_type": "code",
            "execution_count": None,
            "id": "a1b2c3d4",
            "metadata": {},
            "outputs": [],
            "source": [],
        }],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return (json.dumps(notebook, indent=1) + "\n").encode("utf-8")


# --------------------------------------------------------------------------
# The menu. File name minus extension = label in "New Document".
# --------------------------------------------------------------------------

TEMPLATES: List[Template] = [
    # Windows "New" menu equivalents
    Template("Microsoft Word Document.docx", "windows", build_docx,
             "Blank Word document (Letter or A4, Calibri 11)"),
    Template("Microsoft Excel Worksheet.xlsx", "windows", build_xlsx,
             "Blank workbook with Sheet1"),
    Template("Microsoft PowerPoint Presentation.pptx", "windows", build_pptx,
             "16:9 deck with one title slide"),
    Template("Bitmap image.png", "windows", build_png,
             "White canvas (PNG; opens in any image editor)"),
    Template("SQLite Database.sqlite3", "windows", build_sqlite,
             "Empty SQLite database (stands in for Access)"),
    Template("Text Document.txt", "windows", _text(""),
             "Empty text file"),
    # Extras for Python / R / data work
    Template("Python Script.py", "extras", _text(PYTHON_SCRIPT),
             "Script skeleton with main()"),
    Template("R Script.R", "extras", _text(R_SCRIPT),
             "R script with Rscript shebang"),
    Template("Jupyter Notebook.ipynb", "extras", build_ipynb,
             "Notebook (nbformat 4.5, Python 3 kernel)"),
    Template("Quarto Document.qmd", "extras", _text(QUARTO_DOC),
             "Quarto document with YAML header"),
    Template("R Markdown Document.Rmd", "extras", _text(RMARKDOWN_DOC),
             "R Markdown with YAML header"),
    Template("Markdown Document.md", "extras", _text(""),
             "Empty Markdown file"),
    Template("CSV File.csv", "extras", _text(""),
             "Empty CSV file"),
]


def select_templates(include_extras: bool, group_extras: bool) -> Dict[str, Template]:
    """Map relative path inside the Templates folder -> Template."""
    chosen: Dict[str, Template] = {}
    for t in TEMPLATES:
        if t.group == "extras":
            if not include_extras:
                continue
            rel = f"{EXTRAS_FOLDER}/{t.filename}" if group_extras else t.filename
        else:
            rel = t.filename
        chosen[rel] = t
    return chosen


# --------------------------------------------------------------------------
# Locations, manifest, safe writes
# --------------------------------------------------------------------------

def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def _manifest_path() -> Path:
    return _data_dir() / "manifest.json"


def _user_dirs_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "user-dirs.dirs"


def resolve_templates_dir() -> Tuple[Path, Optional[str]]:
    """Return (folder, problem). `problem` explains why the folder still
    has to be registered with xdg-user-dirs; None means it already is."""
    home = Path.home()
    cfg = _user_dirs_file()
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r'\s*XDG_TEMPLATES_DIR\s*=\s*"(.*)"\s*$', line)
            if not m:
                continue
            path = Path(m.group(1).replace("$HOME", str(home))).expanduser()
            if not path.is_absolute():
                path = home / path
            if path.resolve() == home.resolve():
                return home / "Templates", "it was disabled (pointed at your home folder)"
            return path, None
    return home / "Templates", "none was registered"


def register_templates_dir(path: Path) -> str:
    exe = shutil.which("xdg-user-dirs-update")
    if exe:
        done = subprocess.run([exe, "--set", "TEMPLATES", str(path)],
                              capture_output=True, text=True)
        if done.returncode == 0:
            return "xdg-user-dirs-update"
    # Fallback: edit user-dirs.dirs ourselves.
    cfg = _user_dirs_file()
    home = Path.home()
    try:
        value = "$HOME/" + path.relative_to(home).as_posix()
    except ValueError:
        value = str(path)
    entry = f'XDG_TEMPLATES_DIR="{value}"'
    lines = cfg.read_text(encoding="utf-8").splitlines() if cfg.is_file() else []
    out: List[str] = []
    replaced = False
    for line in lines:
        if re.match(r"\s*XDG_TEMPLATES_DIR\s*=", line):
            if not replaced:
                out.append(entry)
                replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(entry)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(cfg)


def load_manifest() -> dict:
    path = _manifest_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") == MANIFEST_VERSION:
                return data
        except (OSError, ValueError):
            pass
    return {"version": MANIFEST_VERSION, "templates_dir": None, "files": {}, "dirs": []}


def save_manifest(manifest: dict) -> None:
    _write_atomic(_manifest_path(),
                  (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


_BACKUP_STAMP = time.strftime("%Y%m%d-%H%M%S")


def _backup(path: Path, rel: str) -> Path:
    dest = _data_dir() / "backup" / _BACKUP_STAMP / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def _report(status: str, rel: str, note: str = "") -> None:
    print(f"  {status:<10} {rel}" + (f"  ({note})" if note else ""))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    opts = Options(paper=args.paper, bitmap_size=args.bitmap_size)
    manifest = load_manifest()

    if args.dest:
        tdir, problem = Path(args.dest).expanduser().resolve(), None
    else:
        tdir, problem = resolve_templates_dir()
    if problem:
        how = register_templates_dir(tdir)
        print(f"Registered {tdir} as your Templates folder ({problem}; via {how}).")
    tdir.mkdir(parents=True, exist_ok=True)
    print(f"Templates folder: {tdir}")

    selection = select_templates(not args.no_extras, args.group_extras)
    old_dir = Path(manifest["templates_dir"]) if manifest.get("templates_dir") else tdir
    old_files: Dict[str, str] = dict(manifest.get("files", {}))
    same_dir = old_dir == tdir
    owned_dirs = set(manifest.get("dirs", [])) if same_dir else set()

    if args.group_extras and not args.no_extras and not (tdir / EXTRAS_FOLDER).exists():
        owned_dirs.add(EXTRAS_FOLDER)

    new_files: Dict[str, str] = {}
    counts = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0, "removed": 0}

    for rel, template in selection.items():
        target = tdir / rel
        data = template.build(opts)
        digest = _sha256(data)
        if target.is_dir():
            _report("skipped", rel, "a folder with this name exists")
            counts["skipped"] += 1
            continue
        if target.exists():
            current = _file_sha256(target)
            if current == digest:
                new_files[rel] = digest
                _report("unchanged", rel)
                counts["unchanged"] += 1
                continue
            ours = same_dir and old_files.get(rel) == current
            if not ours and not args.force:
                _report("skipped", rel,
                        "a different file with this name is already there; "
                        "--force replaces it after a backup")
                counts["skipped"] += 1
                continue
            note = "" if ours else f"previous file backed up to {_backup(target, rel)}"
            _write_atomic(target, data)
            new_files[rel] = digest
            _report("updated", rel, note)
            counts["updated"] += 1
        else:
            _write_atomic(target, data)
            new_files[rel] = digest
            _report("added", rel)
            counts["added"] += 1

    # Remove files from an earlier install that are no longer selected
    # (e.g. --no-extras now, or --group-extras toggled), if unmodified.
    for rel, digest in old_files.items():
        if same_dir and rel in selection:
            continue
        path = old_dir / rel
        if not path.is_file():
            continue
        if _file_sha256(path) == digest:
            path.unlink()
            _report("removed", rel, "no longer selected")
            counts["removed"] += 1
        else:
            _report("kept", rel, "no longer managed; you had edited it")
    for d in sorted(set(manifest.get("dirs", [])) | owned_dirs):
        if d not in {Path(r).parent.as_posix() for r in new_files}:
            for base in {old_dir, tdir}:
                try:
                    (base / d).rmdir()
                    owned_dirs.discard(d)
                except OSError:
                    pass

    save_manifest({
        "version": MANIFEST_VERSION,
        "templates_dir": str(tdir),
        "files": new_files,
        "dirs": sorted(d for d in owned_dirs if (tdir / d).is_dir()),
    })
    summary = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
    print(f"Done: {summary}.")
    print('Right-click in Files or on the desktop and open "New Document" to use them.')
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    files: Dict[str, str] = manifest.get("files", {})
    if not manifest.get("templates_dir"):
        print("Nothing to uninstall: no install record found.")
        return 0
    tdir = Path(manifest["templates_dir"])
    print(f"Templates folder: {tdir}")
    kept: Dict[str, str] = {}
    for rel, digest in sorted(files.items()):
        path = tdir / rel
        if not path.is_file():
            _report("missing", rel)
            continue
        if _file_sha256(path) == digest:
            path.unlink()
            _report("removed", rel)
        elif args.force:
            saved = _backup(path, rel)
            path.unlink()
            _report("removed", rel, f"your edited copy is saved at {saved}")
        else:
            kept[rel] = digest
            _report("kept", rel, "you edited it; --force removes it after a backup")
    for d in manifest.get("dirs", []):
        try:
            (tdir / d).rmdir()
        except OSError:
            pass
    if kept:
        manifest["files"] = kept
        save_manifest(manifest)
    else:
        _manifest_path().unlink(missing_ok=True)
        try:
            _data_dir().rmdir()
        except OSError:
            pass
    print("Done. Your Templates folder itself was left in place.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    installed = {Path(rel).name for rel in manifest.get("files", {})}
    print(f'{"Menu label":<36}{"Extension":<11}{"Group":<9}Status')
    for t in TEMPLATES:
        ext = "." + t.filename.rsplit(".", 1)[1]
        status = "installed" if t.filename in installed else "-"
        print(f"{t.label:<36}{ext:<11}{t.group:<9}{status}")
        print(f'{"":<36}{t.note}')
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    opts = Options(paper=args.paper, bitmap_size=args.bitmap_size)
    out = Path(args.out_dir).expanduser()
    for rel, template in select_templates(not args.no_extras, args.group_extras).items():
        data = template.build(opts)
        _write_atomic(out / rel, data)
        print(f"  {len(data):>8,} B  {out / rel}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _size(text: str) -> Tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", text)
    if not m:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 1920x1080")
    w, h = int(m.group(1)), int(m.group(2))
    if not (1 <= w <= 10000 and 1 <= h <= 10000):
        raise argparse.ArgumentTypeError("width and height must be 1-10000")
    return w, h


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='Right-Click New: Windows-style "New" templates for GNOME Files and the Ubuntu desktop.')
    sub = parser.add_subparsers(dest="command", required=True)

    def content_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--no-extras", action="store_true",
                       help="only the Windows-equivalent items (no Python/R/data files)")
        p.add_argument("--group-extras", action="store_true",
                       help=f'put the extras in a "{EXTRAS_FOLDER}" submenu')
        p.add_argument("--paper", choices=sorted(PAPER_TWIPS), default="letter",
                       help="page size of the Word template (default: letter)")
        p.add_argument("--bitmap-size", type=_size, default=(1920, 1080),
                       metavar="WxH", help="canvas size of the bitmap (default: 1920x1080)")

    p_install = sub.add_parser("install", help="add templates to your Templates folder")
    content_options(p_install)
    p_install.add_argument("--force", action="store_true",
                           help="replace same-named files (backed up first)")
    p_install.add_argument("--dest", metavar="DIR",
                           help="install into DIR instead of the XDG Templates folder")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="remove the templates this script added")
    p_uninstall.add_argument("--force", action="store_true",
                             help="also remove templates you edited (backed up first)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_list = sub.add_parser("list", help="show the available templates")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="write the files to OUT_DIR only")
    content_options(p_build)
    p_build.add_argument("out_dir", metavar="OUT_DIR")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
