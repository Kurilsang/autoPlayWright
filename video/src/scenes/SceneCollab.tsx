import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {StepPipeline} from '../components/StepPipeline';
import {Chip} from '../components/Bits';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const steps = [
  {
    n: '1',
    title: '探页面',
    desc: '写 configs/crawl/<page>_probe.yaml，探查原语推进状态 + dump_dom，产出页面状态快照。',
    hint: 'python -m apw.crawler',
  },
  {
    n: '2',
    title: '补定位器',
    desc: 'locators/<page>.yaml：候选按优先级书写，来源标 manual / ai，禁止散落裸 selector。',
    hint: 'testid > role+name > …',
  },
  {
    n: '3',
    title: '补页面对象',
    desc: 'src/apw/pages/<page>.py：动作 = 语义原语（完成判定 + 失败取证），注册进 default_registry()。',
    hint: 'engine/registry.py',
  },
  {
    n: '4',
    title: '写 flow',
    desc: 'flows/<case>.yaml：do / assert / judge，只断言确定性内容；LLM 产出只进 capture_context 证据。',
    hint: '同页面新链路从这步起',
  },
  {
    n: '5',
    title: '过验收门',
    desc: '收集期 schema 校验 + ruff check + 真实环境绿跑 ≥3 次（防偶发卡死污染结论），绿了才合入。',
    hint: 'D15 验收门',
  },
];

const rules = [
  '凭据与内网信息永不入库',
  '失败即取证，禁止自愈',
  '页面元素一律走定位器仓库',
  '引擎不 import pytest / allure',
  '并发 worker ≤ 5（限流）',
  'commit：feat/fix + 一句话要点',
];

export const SceneCollab: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[6].chapter}
      title="团队怎么协作：新增一条核心链路"
      subtitle="固定五步走，人人（含 AI）走同一条路；评审与验收门是唯一入库通道。"
      duration={SCENES[6].duration}
    >
      <StepPipeline steps={steps} startDelay={20} stepDelay={58} />
      <Reveal delay={370} y={20}>
        <div
          style={{
            marginTop: 40,
            display: 'flex',
            alignItems: 'center',
            gap: 18,
          }}
        >
          <div
            style={{
              fontSize: 23,
              fontWeight: 800,
              color: COLORS.warn,
              letterSpacing: 1,
            }}
          >
            硬约束（人人适用）
          </div>
          <div style={{flex: 1, height: 2, background: 'rgba(159,176,204,0.25)'}} />
        </div>
      </Reveal>
      <Reveal delay={396} y={18}>
        <div style={{marginTop: 20, display: 'flex', gap: 14, flexWrap: 'wrap'}}>
          {rules.map((r) => (
            <Chip key={r} label={r} tone="warn" fontSize={20} />
          ))}
        </div>
      </Reveal>
      <Reveal delay={446} y={16}>
        <div
          style={{
            marginTop: 30,
            fontSize: 23,
            color: COLORS.dim,
            lineHeight: 1.55,
          }}
        >
          AI 的权限边界（D10）：只修资产、不改现场——失败后产出修复 diff 人工审合入；
          探索区临时脚本用完归档 <span style={{color: COLORS.accent}}>.scratch/</span>{' '}
          当生成器素材，升格需人工判定。
        </div>
      </Reveal>
    </SceneShell>
  );
};
