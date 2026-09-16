"""Export current review documents without API calls or changing old artifacts."""
import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--browser', default=str(Path.home()/'.cache/ms-playwright/chromium-1187/chrome-linux/chrome'))
    ap.add_argument('--font', type=Path, default=ROOT/'.tmp/fonts/NotoSansCJKsc-Regular.otf')
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    from markdown_it import MarkdownIt
    from fontTools import subset
    from playwright.sync_api import sync_playwright
    documents = [('outline_zh','yujia-paper-outline-2026-09-04.md'),('progress','yujia-progress-2026-09-15.md')]
    slide_source = ROOT/'results/real/yujia_meeting_2026_09_04/slides.html'
    options = subset.Options()
    options.flavor = 'woff2'
    font = subset.load_font(str(args.font), options)
    for record in font['name'].names:
        if record.nameID in {1, 4, 6, 16}:
            record.string = 'MemoryReviewCJK'.encode(record.getEncoding())
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=''.join((ROOT/'docs'/name).read_text() for _,name in documents)+slide_source.read_text())
    subsetter.subset(font)
    fontpath = out/'review-cjk.woff2'
    subset.save_font(font, str(fontpath), options)
    shutil.copyfile(args.font.parent/'LICENSE', out/'FONT-LICENSE.txt')
    font_css = '@font-face{font-family:ReviewCJK;src:url(data:font/woff2;base64,'+base64.b64encode(fontpath.read_bytes()).decode()+') format("woff2");font-weight:normal;font-style:normal;font-display:block}body{font-family:ReviewCJK,system-ui,sans-serif}code,pre{font-family:ui-monospace,ReviewCJK,monospace}'
    libraries = ROOT/'.tmp/chromium-libs'
    os.environ['LD_LIBRARY_PATH'] = ':'.join([str(libraries/'usr/lib64'), str(libraries/'lib64'), os.environ.get('LD_LIBRARY_PATH','')])
    style = '''body{max-width:1000px;margin:40px auto;padding:0 35px;color:#203149;background:white;font:16px/1.75 system-ui,sans-serif}h1{font-size:30px;line-height:1.3}h2{font-size:22px;margin-top:30px}a{color:#245c91;text-decoration:none}blockquote{border-left:3px solid #b8cadd;margin:20px 0;padding:0 18px;color:#435871}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.6}td,th{padding:9px;border:1px solid #c5cfdb;text-align:left;vertical-align:top}th{background:#edf2f7}code{font-size:.88em;overflow-wrap:anywhere}tr{break-inside:avoid}@media print{@page{size:A4;margin:17mm 14mm 19mm}body{margin:0;padding:0;font-size:10.5pt;line-height:1.55;max-width:none}h1{font-size:20pt}h2{font-size:14pt;break-after:avoid}table{font-size:9pt}td,th{padding:5px}a{color:inherit}p{orphans:3;widows:3}blockquote{break-inside:avoid}}'''
    manifest = {'purpose':'offline review documents; no new experimental results','documents':[],
                'font':{'source':'https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf',
                        'source_sha256':hashlib.sha256(args.font.read_bytes()).hexdigest(),
                        'subset_sha256':hashlib.sha256(fontpath.read_bytes()).hexdigest(),'license':'FONT-LICENSE.txt'}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,executable_path=args.browser,args=['--no-sandbox','--disable-gpu'])
        for name,filename in documents:
            src = ROOT/'docs'/filename
            md = MarkdownIt('commonmark', {'html':False}).enable('table')
            tokens = md.parse(src.read_text())
            def resolve(tokens):
                for t in tokens:
                    if t.type=='link_open':
                        href=t.attrGet('href')
                        if not urlsplit(href).scheme and not href.startswith('#'):
                            parts=urlsplit(href)
                            target=(src.parent/unquote(parts.path)).resolve()
                            if not target.exists():raise FileNotFoundError(target)
                            t.attrSet('href',target.as_uri()+('#'+parts.fragment if parts.fragment else ''))
                    if t.children:resolve(t.children)
            resolve(tokens)
            body=md.renderer.render(tokens,md.options,{})
            pagepath=out/(name+'.html')
            pagepath.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+html.escape(filename)+'</title><style>'+style+font_css+'</style><main>'+body+'</main></html>')
            page=browser.new_page(viewport={'width':1100,'height':1400},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(pagepath.as_uri())
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.fonts.check("16px ReviewCJK", "实验余额记忆")')
            assert not errors,errors
            assert '余额不足' in page.inner_text('main')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.pdf(path=str(out/(name+'.pdf')),print_background=True,prefer_css_page_size=True,display_header_footer=True,header_template='<div></div>',footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#666"><span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            page.screenshot(path=str(out/(name+'-preview.png')))
            manifest['documents'].append({'source':str(src.relative_to(ROOT)),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'pdf':name+'.pdf','pdf_sha256':hashlib.sha256((out/(name+'.pdf')).read_bytes()).hexdigest(),'browser_errors':errors,'links_checked':True})
            page.close()
        # Preserve the historical scientific evidence byte-for-byte; only add
        # portable display fonts and an explicit status label to its HTML copy.
        slide_html = slide_source.read_text().replace('</style>',font_css+'body{font-family:Arial,ReviewCJK,sans-serif}</style>',1)
        slide_html = slide_html.replace('September 4 meeting · evidence slides','Historical read-side / risk illustration · new formal comparison pending',1)
        (out/'illustrative_slides.html').write_text(slide_html)
        shutil.copyfile(slide_source.parent/'evidence.json',out/'evidence.json')
        page=browser.new_page(viewport={'width':1400,'height':900})
        page.goto((out/'illustrative_slides.html').as_uri())
        page.evaluate('document.fonts.ready')
        page.pdf(path=str(out/'illustrative_slides.pdf'),print_background=True,prefer_css_page_size=True)
        for i,slide in enumerate(page.locator('.slide').all(),1):
            slide.screenshot(path=str(out/f'illustration-{i}.png'))
        manifest['historical_illustration']={'source':str(slide_source.relative_to(ROOT)),
            'source_sha256':hashlib.sha256(slide_source.read_bytes()).hexdigest(),
            'evidence_sha256':hashlib.sha256((out/'evidence.json').read_bytes()).hexdigest(),
            'scope':'unchanged historical read-side and risk evidence; no new model outcomes'}
        page.close()
        browser.close()
    (out/'export_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':
    main()
