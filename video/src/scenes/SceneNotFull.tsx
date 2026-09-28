import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {Card} from '../components/Bits';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const pains = [
  {
    badge: '成本',
    tone: 'warn' as const,
    title: 'UI 高频改版',
    body: '页面一改，全量用例成片变红，维护成本超过回归收益。D11 的判断：靠数量堆不出稳定。',
  },
  {
    badge: '限流',
    tone: 'bad' as const,
    title: '后端 LLM 限流是硬约束',
    body: '3~5 并发即触发限流，xdist 并行度被锁死（默认 3、硬上限 5）。用例越多，全量跑得越久。',
  },
  {
    badge: '噪声',
    tone: 'bad' as const,
    title: '假失败有毒',
    body: 'LLM 非确定 + 半截渲染，海量断言 = 海量噪声。红了没人看，用例就废了。',
  },
];

const strategies = [
  {
    tone: 'good' as const,
    title: '定位器多候选回退',
    body: 'testid > role+name > placeholder/label > text > css/xpath，改版只修定位器仓库。',
  },
  {
    tone: 'good' as const,
    title: '断言只打稳定结构标记',
    body: '组件 / 状态 / 结构，不碰 LLM 措辞；基础原语必须以 assert 收口。',
  },
  {
    tone: 'good' as const,
    title: '用例总量控制',
    body: 'v1 只做 20~50 条核心链路，按 P0/P1 分级，冒烟与全量分开跑。',
  },
];

export const SceneNotFull: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[4].chapter}
      title="为什么不做全量覆盖？"
      subtitle="不是能力问题，是性价比问题：全量在高频改版 + LLM 限流的现实里跑不动、也守不住。"
      duration={SCENES[4].duration}
    >
      <div style={{display: 'flex', gap: 26}}>
        {pains.map((p, i) => (
          <Reveal key={p.title} delay={16 + i * 24} y={26} style={{flex: 1}}>
            <Card {...p} height={212} />
          </Reveal>
        ))}
      </div>
      <Reveal delay={110} y={18}>
        <div
          style={{
            marginTop: 34,
            display: 'flex',
            alignItems: 'center',
            gap: 18,
          }}
        >
          <div
            style={{
              fontSize: 24,
              fontWeight: 800,
              color: COLORS.accent2,
              letterSpacing: 2,
            }}
          >
            对策（D11 定稿）
          </div>
          <div
            style={{
              flex: 1,
              height: 2,
              background: 'rgba(159,176,204,0.25)',
            }}
          />
        </div>
      </Reveal>
      <div style={{display: 'flex', gap: 26, marginTop: 22}}>
        {strategies.map((s, i) => (
          <Reveal key={s.title} delay={130 + i * 24} y={24} style={{flex: 1}}>
            <Card {...s} height={172} />
          </Reveal>
        ))}
      </div>
      <Reveal delay={230} y={20}>
        <div
          style={{
            marginTop: 32,
            background: 'rgba(55,214,166,0.10)',
            border: '1px solid rgba(55,214,166,0.35)',
            borderRadius: 16,
            padding: '20px 30px',
            fontSize: 27,
            lineHeight: 1.5,
            fontWeight: 650,
          }}
        >
          原则：只测外部行为——
          <span style={{color: COLORS.accent2}}>
            核心链路先绿、且持续可信，比用例数量更重要。
          </span>
        </div>
      </Reveal>
    </SceneShell>
  );
};
