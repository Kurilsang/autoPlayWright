"""页面 DOM 提取：语义化交互元素 + 定位器候选（按选择器优先级）+ 状态片段。

只做数据采集，不含业务判断；候选优先级 testid > role+name > placeholder/label >
text > css/xpath（与定位器仓库约定一致），产出可直接映射 `locators/` 格式。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

_EXTRACT_JS = r"""
() => {
  const sel = 'a, button, input, textarea, select, summary,' +
    ' [role], [tabindex]:not([tabindex="-1"]), [data-testid],' +
    ' ul[class], ol[class], [class*="message"]';
  const implicitRole = (el, tag) => {
    if (el.getAttribute('role')) return el.getAttribute('role');
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : '';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return 'combobox';
    if (tag === 'input') return ({
      text: 'textbox', search: 'textbox', email: 'textbox', number: 'textbox',
      checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button',
    })[el.type] || '';
    return '';
  };
  const regionOf = (el) => {
    if (el.closest('dialog, [role="dialog"]')) return 'dialog';
    if (el.closest('header, [role="banner"]')) return 'header';
    if (el.closest('nav, aside')) return 'sidebar';
    if (el.closest('footer, form, [class*="composer"], [class*="input-area"]'))
      return 'composer';
    if (el.closest('main, [role="main"]')) {
      return el.closest('[class*="message"], [id*="message"], [data-testid*="message"]')
        ? 'message_list' : 'content';
    }
    return 'other';
  };
  const slug = (s) => (s || '').toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24);

  const elements = [];
  document.querySelectorAll(sel).forEach(el => {
    const tag = el.tagName.toLowerCase();
    const testid = el.getAttribute('data-testid') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const aria = el.getAttribute('aria-label') || '';
    const title = el.getAttribute('title') || '';
    let label = '';
    if (el.id) {
      const lab = document.querySelector('label[for="' + el.id + '"]');
      if (lab) label = (lab.textContent || '').trim().replace(/\s+/g, ' ');
    }
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const role = implicitRole(el, tag);
    const name = aria || label || title || ((tag === 'input' || tag === 'textarea') ? '' : text);

    const candidates = [];
    if (testid) candidates.push({by: 'testid', value: testid});
    if (role && name) candidates.push({by: 'role', value: role, name: name.slice(0, 60)});
    if (placeholder) candidates.push({by: 'placeholder', value: placeholder});
    if (label) candidates.push({by: 'label', value: label.slice(0, 60)});
    if (!testid && name && name.length <= 24)
      candidates.push({by: 'text', value: name, exact: true});
    let css = tag;
    if (el.id) {
      css = tag + '#' + el.id;
    } else {
      const cls = Array.from(el.classList || []).slice(0, 3);
      if (cls.length) css += '.' + cls.join('.');
    }
    candidates.push({by: 'css', value: css});

    elements.push({
      name_hint: slug(testid || placeholder || name || text || (role + '_' + tag)),
      region: regionOf(el),
      role, accessible_name: (name || '').slice(0, 120),
      testid, placeholder, tag,
      classes: Array.from(el.classList || []).slice(0, 6),
      text,
      interactable: ['a', 'button', 'input', 'textarea', 'select', 'summary']
        .includes(tag) || el.hasAttribute('onclick') || el.hasAttribute('tabindex'),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      candidates,
    });
  });
  const main = document.querySelector('main') || document.body;
  return {
    url: location.href, route: location.pathname,
    title: document.title, elements,
    dom_excerpt: main.outerHTML,
  };
}
"""


def extract_page(page: Page) -> dict:
    """采集当前页面快照原始数据（元素/候选/状态 DOM 片段）。"""
    return page.evaluate(_EXTRACT_JS)
