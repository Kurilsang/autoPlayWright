import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {Card} from '../components/Bits';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const cards = [
  {
    badge: '痛点 1',
    tone: 'warn' as const,
    title: '双端产品，页面多、链路多',
    body: 'Web 端 + Electron 客户端，会话创建、对话、工具调用展示、文档处理、工作流……核心链路成体系地增长。',
  },
  {
    badge: '痛点 2',
    tone: 'bad' as const,
    title: '核心链路零自动化',
    body: '完全没有自动化覆盖，版本一到全靠手工回归。成本高、周期长，且不可持续。',
  },
  {
    badge: '痛点 3',
    tone: 'bad' as const,
    title: 'LLM 回复非确定',
    body: 'Agent 回复由 LLM 生成、措辞每次不同。传统「断言固定文本」的写法会大量假失败，用例写了也不敢信。',
  },
  {
    badge: '痛点 4',
    tone: 'warn' as const,
    title: '逐条手写不现实',
    body: '页面数量大、链路数量多，写用例的速度追不上页面改版的速度，人力线性堆不上去。',
  },
];

export const SceneWhy: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[1].chapter}
      title="为什么要建 autoPlayWright？"
      subtitle="被测对象是内部 Agent 产品的 Web 端与 Electron 客户端——先看清问题，再谈方案。"
      duration={SCENES[1].duration}
    >
      <div style={{display: 'flex', gap: 28}}>
        {[0, 1].map((col) => (
          <div
            key={col}
            style={{flex: 1, display: 'flex', flexDirection: 'column', gap: 26}}
          >
            {cards.slice(col * 2, col * 2 + 2).map((c, i) => (
              <Reveal key={c.title} delay={16 + (col * 2 + i) * 26} y={28}>
                <Card {...c} height={218} />
              </Reveal>
            ))}
          </div>
        ))}
      </div>
      <Reveal delay={136} y={22}>
        <div
          style={{
            marginTop: 38,
            background: 'rgba(91,140,255,0.12)',
            border: '1px solid rgba(91,140,255,0.4)',
            borderRadius: 16,
            padding: '22px 30px',
            fontSize: 28,
            lineHeight: 1.5,
            fontWeight: 650,
          }}
        >
          结论：靠人肉回归撑不住，需要一套{' '}
          <span style={{color: COLORS.accent2}}>可复用、可判信、可持续维护</span>{' '}
          的链路自动化资产。
        </div>
      </Reveal>
    </SceneShell>
  );
};
